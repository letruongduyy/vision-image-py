from datetime import datetime
import os
import requests
from bs4 import BeautifulSoup

# --- Import helper modules ---
from text_utils import normalize_text
from common import log_section
from court_case_detect.detect import detect

import boto3


def parse_filename_metadata(filename):
    name = filename.replace(".html", "")
    parts = name.split(" ", 1)

    if len(parts) < 2:
        return None

    raw_date = parts[0]
    court_text = parts[1]

    parsed_date = None
    for fmt in ("%d_%m_%Y", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(raw_date, fmt)
            break
        except Exception:
            continue

    if not parsed_date:
        return None

    return {
        "court_text": court_text,
        "date": parsed_date,
    }


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

    collection = get_mongo_collection("court_hearings")

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

    # --- LOCAL FILE MODE ---
    folder_paths = [
        "/Users/missyou/Downloads/OneDrive_1_1-3-2026/Daily Court List 2024",
        "/Users/missyou/Downloads/OneDrive_1_1-3-2026/Daily court list 2025",
    ]

    court_values = []

    print(f"Processing court lists from folders: {folder_paths}")
    total_files = 0

    for folder_path in folder_paths:
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                if not filename.endswith(".html"):
                    continue

                total_files += 1

                file_path = os.path.join(root, filename)
                file_size = os.path.getsize(file_path)
                print(f"File: {filename} | Size: {file_size} bytes")

                print(f"Counting file: {file_path}")
                meta = parse_filename_metadata(filename)

                print(meta)
                if not meta:
                    continue

                court_values.append(
                    {
                        "value": meta["court_text"],
                        "text": meta["court_text"],
                        "date": meta["date"],
                        "file_path": file_path,
                    }
                )

    print(f"Total HTML files (all .html): {total_files}")
    print(f"Total valid parsed files: {len(court_values)}")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://e-services.judiciary.hk/dcl/index.jsp",
    }

    # Removed the block that fetches court list from URL and assigns court_values

    inserted_cases_by_court = {}
    total_inserted_cases = 0
    total_failed_cases = 0

    for court in court_values:
        print(court)
        inserted_cases = []
        failed_cases = []

        try:
            with open(court["file_path"], "r", encoding="utf-8") as f:
                html = f.read()

            view_soup = BeautifulSoup(html, "html.parser")
            cases = detect(view_soup, court)

            # attach createDate and updateDate as current datetime
            for case in cases:
                print("-- CASE BEFORE TIMESTAMP ATTACH ---")
                print(court["date"])
                print("-----------------------------")
                now = datetime.now()
                combined_datetime = court["date"].replace(
                    hour=now.hour,
                    minute=now.minute,
                    second=now.second,
                    microsecond=now.microsecond,
                )
                formatted_datetime = combined_datetime.strftime("%Y-%m-%d %H:%M:%S")
                case["createDate"] = formatted_datetime
                case["updateDate"] = formatted_datetime
                print(case)
            result = {
                "ok": True,
                "court": court,
                "content_length": len(html),
                "cases": cases,
            }
        except Exception as e:
            result = {
                "ok": False,
                "court": court,
                "reason": f"Exception: {e}",
            }

        if result.get("ok") and result.get("cases"):
            log_section(
                "INSERT DB",
                f"{court['value']} - Inserting {len(result['cases'])} cases",
            )

            try:
                insert_result = collection.insert_many(result["cases"], ordered=False)
                inserted_cases.extend(result["cases"])
                log_section(
                    "INSERT SUCCESS",
                    f"{court['value']} - Inserted {len(insert_result.inserted_ids)} cases",
                )
            except Exception as e:
                failed_cases.extend(result["cases"])
                log_section(
                    "INSERT FAILED",
                    f"{court['value']} - Error: {e}",
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

    print(f"TOTAL INSERTED CASES: {total_inserted_cases}")
    print(f"TOTAL FAILED CASES: {total_failed_cases}")

    subject = "Daily feedback from WATCHOR data logging"

    formatted_date = datetime.now().strftime("%-d %b %Y")  # Linux (Lambda ok)

    lines = []
    lines.append(f"Date: {formatted_date}")
    lines.append(f"Total court lists observed: {len(court_values)}")
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

    # emailResponse = sesClient.send_email(
    #     Source="no-reply@ocr.dwyrtbtctf.hk",
    #     # Destination={"ToAddresses": verified_emails},
    #     Destination={"BccAddresses": verified_emails},
    #     Message={
    #         "Subject": {"Data": subject, "Charset": "UTF-8"},
    #         "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
    #     },
    # )
    # log_section("SEND EMAIL RESPONSE", emailResponse)


if __name__ == "__main__":
    lambda_handler({}, {})
