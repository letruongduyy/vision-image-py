from datetime import datetime
import requests
from bs4 import BeautifulSoup

import boto3

def log_section(title: str, data=None):
    print("=" * 67)
    print(title.upper())
    if data is not None:
        print(data)
    print("=" * 67)


def lambda_handler(event, context):
    from mongo_client import get_mongo_collection

    sesClient = boto3.client("ses", region_name="ap-southeast-1")

    collection = get_mongo_collection()

    # Aggregation containers for reporting
    success_stats = []  # list of dicts: {court, courtText, content_length}
    fail_stats = []  # list of dicts: {court, courtText, reason}
    court_values = []  # will be populated if the select exists

    # Use the current date in the required format
    current_date = datetime.now().strftime("%d%m%Y")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://e-services.judiciary.hk/dcl/index.jsp",
    }

    # Construct the URL with the current date parameter
    url = f"https://e-services.judiciary.hk/dcl/index.jsp?lang=en&date={current_date}&mode=view&court=null"

    log_section("FETCH COURT LIST", url)

    # Send the initial GET request to the URL
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the <select> element by its ID 'dclCourt'
    select_element = soup.find("select", {"id": "dclCourt"})

    # Get all <option> values inside the <select> element and store them in a list

    if select_element:
        options = select_element.find_all("option")
        court_values = [
            {"value": option.get("value"), "text": option.get_text(strip=True)}
            for option in options
            if option.get("value")
        ]

        if court_values:
            log_section("ALL COURTS", court_values)
            total_courts = len(court_values)

            # Loop through a list of courts
            for i, court in enumerate(court_values):
                next_court = (
                    court_values[i + 1]["value"] if i + 1 < len(court_values) else None
                )
                remaining = total_courts - (i + 1)
                view_url = f"https://e-services.judiciary.hk/dcl/view.jsp?lang=en&date={current_date}&court={court['value']}"

                log_section(
                    "FETCH COURT",
                    f"Current: {court['value']} → Next: {next_court} | Remaining: {remaining}",
                )

                log_section("URL", view_url)

                # Send GET request with headers and cookies from the initial response
                try:
                    view_response = requests.get(
                        view_url, headers=headers, cookies=response.cookies, timeout=30
                    )

                    log_section(
                        f"FETCH STATUS {court['value']}", view_response.status_code
                    )

                    if view_response.status_code == 200:
                        log_section("COME HERE 1")
                        html = view_response.text
                        log_section("COME HERE 2")
                        content_length = len(html)
                        log_section("COME HERE 3")
                        view_soup = BeautifulSoup(html, "html.parser")
                        log_section("COME HERE 4")
                        content = view_soup.get_text(separator=" ", strip=True)
                        log_section("COME HERE 5")
                        log_section(f"FETCH SUCCESS {court['value']}")

                        # Insert raw page capture per court
                        collection.insert_one(
                            {
                                "court": court["value"],
                                "date": current_date,
                                "content": content,
                                "html": html,
                                "courtText": court["text"],
                                "createDate": timestamp,
                                "updateDate": timestamp,
                                "contentLength": content_length,
                            }
                        )

                        success_stats.append(
                            {
                                "court": court["value"],
                                "courtText": court["text"],
                                "content_length": content_length,
                            }
                        )
                    else:
                        reason = f"HTTP {view_response.status_code}"
                        log_section(
                            f"FETCH FAILED {court['value']}", view_response.status_code
                        )
                        fail_stats.append(
                            {
                                "court": court["value"],
                                "courtText": court["text"],
                                "reason": reason,
                            }
                        )
                except Exception as e:
                    reason = f"Exception: {e}"
                    log_section(f"FETCH EXCEPTION {court['value']}", reason)
                    fail_stats.append(
                        {
                            "court": court["value"],
                            "courtText": court["text"],
                            "reason": reason,
                        }
                    )

            total_courts = len(court_values)
            processed_ok = len(success_stats)
            processed_fail = len(fail_stats)
        else:
            log_section("NO COURT VALUES FOUND")
            total_courts = 0
            processed_ok = len(success_stats)
            processed_fail = len(fail_stats)
    else:
        log_section("NO COURT VALUES FOUND")
        total_courts = 0
        processed_ok = len(success_stats)
        processed_fail = len(fail_stats)

    # Compose SES email summary after processing
    if processed_fail == 0:
        subject = "Success for court import"
    else:
        subject = "Fail for court import"

    lines = []
    lines.append(f"Date: {current_date} (generated at {timestamp})")
    lines.append(f"Total courts detected: {total_courts}")
    lines.append(f"Processed successfully: {processed_ok}")
    lines.append(f"Failed: {processed_fail}")
    lines.append("")
    lines.append("Court import summary:")

    for court in court_values:
        match = next((s for s in success_stats if s["court"] == court["value"]), None)
        fail = next((f for f in fail_stats if f["court"] == court["value"]), None)
        if match:
            lines.append(f"- {court['text']} ({court['value']}): import success")
        elif fail:
            lines.append(
                f"- {court['text']} ({court['value']}): import failed ({fail['reason']})"
            )
        else:
            lines.append(f"- {court['text']} ({court['value']}): no data")
    lines.append("")

    body_text = "\n".join(lines)

    # emailResponse = sesClient.send_email(
    #     Source="no-reply@ocr.dwyrtbtctf.hk",
    #     Destination={
    #         "ToAddresses": [
    #             "letruongduyy@gmail.com",
    #             "jacky.hui@ddaapp.com",
    #             "calvinlaw4118@hotmail.com"
    #         ]
    #     },
    #     Message={
    #         "Subject": {"Data": subject, "Charset": "UTF-8"},
    #         "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
    #     },
    # )
    # log_section("SEND EMAIL RESPONSE", emailResponse)


if __name__ == "__main__":
    lambda_handler({}, {})
