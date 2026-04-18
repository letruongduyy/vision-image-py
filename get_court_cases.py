from datetime import datetime
import requests
from bs4 import BeautifulSoup

# --- Import helper modules ---
from text_utils import normalize_text
from common import log_section
from court_case_detect.detect import detect

import boto3


def fetch_and_parse_court(court, current_date, headers, cookies):
    view_url = f"https://e-services.judiciary.hk/dcl/view.jsp?lang=en&date={current_date}&court={court['value']}"

    log_section(
        "FETCH COURT",
        f"Court: {court['value']} ({court['text']})",
    )
    log_section("URL", view_url)

    try:
        view_response = requests.get(
            view_url, headers=headers, cookies=cookies, timeout=30
        )

        log_section(f"FETCH STATUS {court['value']}", view_response.status_code)

        if view_response.status_code != 200:
            return {
                "ok": False,
                "court": court,
                "reason": f"HTTP {view_response.status_code}",
            }

        html = view_response.text
        content_length = len(html)
        view_soup = BeautifulSoup(html, "html.parser")

        cases = detect(view_soup, court)

        return {
            "ok": True,
            "court": court,
            "content_length": content_length,
            "cases": cases,
        }

    except Exception as e:
        return {
            "ok": False,
            "court": court,
            "reason": f"Exception: {e}",
        }


def lambda_handler(event, context):
    from mongo_client import get_mongo_collection

    sesClient = boto3.client("ses", region_name="ap-southeast-1")

    # Get verified SES email identities (FROM addresses)
    ses_identities = sesClient.list_identities(IdentityType="EmailAddress").get(
        "Identities", []
    )

    log_section("SES VERIFIED EMAIL IDENTITIES", ses_identities)

    collection = get_mongo_collection()

    # Aggregation containers for reporting
    success_stats = []  # list of dicts: {court, courtText, content_length}
    fail_stats = []  # list of dicts: {court, courtText, reason}
    court_values = []  # will be populated if the select exists
    verified_emails = []
    # Use the current date in the required format
    current_date = datetime.now().strftime("%d%m%Y")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if ses_identities:
        response = sesClient.get_identity_verification_attributes(
            Identities=ses_identities
        )

        verification_attrs = response.get("VerificationAttributes", {})

        verified_emails = [
            email
            for email, attrs in verification_attrs.items()
            if attrs.get("VerificationStatus") == "Success"
        ]

    print(f"Verified SES emails: {verified_emails}")

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
            total_courts = len(court_values)

            inserted_cases_by_court = {}
            total_inserted_cases = 0
            total_failed_cases = 0

            for court in court_values:
                inserted_cases = []
                failed_cases = []

                result = fetch_and_parse_court(
                    court=court,
                    current_date=current_date,
                    headers=headers,
                    cookies=response.cookies,
                )

                if result.get("ok") and result.get("cases"):
                    try:
                        insert_result = collection.insert_many(
                            result["cases"], ordered=False
                        )

                        inserted_ids = set(insert_result.inserted_ids)

                        for case in result["cases"]:
                            if case.get("_id") in inserted_ids:
                                inserted_cases.append(case)
                            else:
                                failed_cases.append(case)

                        log_section(
                            "MONGO INSERT",
                            f"Inserted {len(inserted_cases)} cases, Failed {len(failed_cases)} cases for court {court['value']}",
                        )

                    except Exception as e:
                        failed_cases.extend(result["cases"])
                        log_section(
                            "MONGO INSERT FAILED",
                            f"{court['value']} - {e}",
                        )

                total_inserted_cases += len(inserted_cases)
                total_failed_cases += len(failed_cases)

                if result.get("ok"):
                    success_stats.append(
                        {
                            "court": court["value"],
                            "courtText": court["text"],
                            "content_length": result.get("content_length", 0),
                        }
                    )
                else:
                    fail_stats.append(
                        {
                            "court": court["value"],
                            "courtText": court["text"],
                            "reason": result.get("reason"),
                        }
                    )

                inserted_cases_by_court[court["value"]] = len(inserted_cases)
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

    print(f"TOTAL INSERTED CASES: {total_inserted_cases}")
    print(f"TOTAL FAILED CASES: {total_failed_cases}")

    subject = "Daily feedback from WATCHOR data logging"

    formatted_date = datetime.now().strftime("%-d %b %Y")  # Linux (Lambda ok)

    lines = []
    lines.append(f"Date: {formatted_date}")
    lines.append(f"Total court lists observed: {total_courts}")
    lines.append(f"Recording lists saved: {processed_ok}")
    lines.append(f"Judicial Systematic failure observed: {processed_fail}")
    lines.append("")
    lines.append("")
    lines.append("")
    lines.append("New Litigation Data Summary:")
    lines.append("")

    # For current testing mode, only one court is processed, so inserted_cases is for that court
    for court in court_values:
        match = next((s for s in success_stats if s["court"] == court["value"]), None)
        fail = next((f for f in fail_stats if f["court"] == court["value"]), None)
        if match:
            lines.append(
                f"- {normalize_text(court['text'])} ({court['value']}): import success, cases inserted: {inserted_cases_by_court.get(court['value'], 0)}"
            )
        elif fail:
            lines.append(
                f"- {normalize_text(court['text'])} ({court['value']}): import failed ({fail['reason']})"
            )
        else:
            lines.append(
                f"- {normalize_text(court['text'])} ({court['value']}): no data"
            )
    lines.append("")

    body_text = "\n".join(lines)

    print(body_text)

    emailResponse = sesClient.send_email(
        Source="no-reply@ocr.dwyrtbtctf.hk",
        # Destination={"ToAddresses": verified_emails},
        Destination={"BccAddresses": verified_emails},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
        },
    )
    log_section("SEND EMAIL RESPONSE", emailResponse)


if __name__ == "__main__":
    lambda_handler({}, {})
