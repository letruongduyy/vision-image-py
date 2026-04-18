import re
from header_detection import (
    is_header_row,
    build_column_map,
    detect_court_no_and_master_from_text,
    get_col,
    is_valid_session_time,
    resolve_column_conflicts,
)
from case_builder import build_case_info


# ==========================
# Helper: Trim edge empty TDs only (preserve column indexes)
# ==========================
def trim_edge_empty_cells(cols, raw_texts):
    """
    Remove empty TDs only from the START and END.
    Never remove empty cells in the middle (index safety).
    """
    start = 0
    end = len(raw_texts)

    while start < end and not raw_texts[start]:
        start += 1

    while end > start and not raw_texts[end - 1]:
        end -= 1

    return cols[start:end], raw_texts[start:end]


def trim_until_anchor(cols, raw_texts):
    """
    Remove leading empty TDs until ONE TD before the anchor cell.
    Used when NO valid time exists.
    """
    anchor_idx = None

    for i, cell in enumerate(cols):
        if cell.find("a", attrs={"name": True}):
            anchor_idx = i
            break

    # No anchor found → do nothing
    if anchor_idx is None:
        return cols, raw_texts

    # Keep exactly ONE empty TD before anchor if possible
    start = max(anchor_idx - 1, 0)

    return cols[start:], raw_texts[start:]


def get_expected_col_count_by_court(court_value):
    """
    Return expected column count based on court type.
    This is used to normalize rows and detect abnormal structures.
    """
    COURT_COLUMN_COUNT = {
        # Magistrates Courts
        "CRC": 6,
        "OAT": 6,
        "ALLMAG": 5,
        "TMMAG": 5,
        "FLMAG": 5,
        "STMAG": 5,
        "WKMAG": 5,
        "KTMAG": 5,
        "KCMAG": 5,
        "ETNMAG": 5,
        "SMT": 6,
        "LT": 4,
        "FMC": 6,
        "DCMC": 7,
        "DC": 7,
        "CT": 7,
        "O14": 4,
        "AJSL": 4,
        "OTD": 4,
        "MIA": 4,
        "CWUP": 4,
        "CRHPI": 4,
        "CLCMC": 4,
        "CLPI": 5,
        "BP": 4,
        "MCL": 5,
        "HCMC": 7,
        "CACFI": 7,
        "CFA": 7,
    }

    return COURT_COLUMN_COUNT.get(court_value, 4)


def should_skip_header_row(col_texts, item_value, header_found):
    """
    Skip non-data rows such as repeated headers, separators, or short noise rows.
    """
    # Empty or meaningless row
    if not col_texts or all(not t for t in col_texts):
        return True

    # Too short to be a real data row
    if len(col_texts) <= 2:
        # For MAG-style courts, short rows often signal header reset
        if (
            item_value
            in (
                "ALLMAG",
                "TMMAG",
                "FLMAG",
                "STMAG",
                "WKMAG",
                "KTMAG",
                "KCMAG",
                "ETNMAG",
            )
            and header_found
        ):
            return True
        return True

    return False


def normalize_row_by_court(cols, raw_texts, court_value, header_found):
    """
    Normalize row structure based on court layout.
    MAG / CFA style courts:
    - If a valid session time exists → trim edge empty cells
    - Otherwise → trim until anchor
    """
    if not header_found:
        return cols, raw_texts

    if court_value not in (
        "ALLMAG",
        "TMMAG",
        "FLMAG",
        "STMAG",
        "WKMAG",
        "KTMAG",
        "KCMAG",
        "ETNMAG",
        "CFA",
    ):
        return cols, raw_texts

    has_valid_time = any(text and is_valid_session_time(text) for text in raw_texts)

    if has_valid_time:
        return trim_edge_empty_cells(cols, raw_texts)

    return trim_until_anchor(cols, raw_texts)


# ==========================
# COURT-SPECIFIC HANDLERS
# ==========================


def detect(soup, item):
    if soup is None:
        return []
    try:
        is_need_find_court = False

        match item.get("value"):
            case (
                "SMT"
                | "LT"
                | "ALLMAG"
                | "TMMAG"
                | "FLMAG"
                | "FLMAG"
                | "STMAG"
                | "WKMAG"
                | "KTMAG"
                | "KCMAG"
                | "ETNMAG"
                | "O14"
                | "AJSL"
                | "OTD"
                | "MIA"
                | "CWUP"
                | "CRHPI"
                | "CLCMC"
                | "CLPI"
                | "BP"
                | "MCL"
            ):
                is_need_find_court = True

        PROTECTED_CONTEXT_KEYS = {"court", "presiding_officer"}

        all_cases = []

        tables = soup.find_all("table")

        if not tables:
            return all_cases

        tr_global_index = 0

        print(f"TOTAL TABLES: {len(tables)}")
        column_map = {}

        prev_values = {
            "court": "",
            "judges": "",
            "master": "",
            "coroner": "",
            "time": "",
            "case_no": "",
            "parties": "",
            "nature": "",
            "representation": "",
            "name_of_deceased": "",
            "claim_no": "",
            "hearing": "",
            "claimant": "",
            "defendant_respondent": "",
            "presiding_officer": "",
            "defendant": "",
            "claimNature": "",
            "suit_application_no": "",
            "claim_nature": "",
        }

        header_found = False
        for _, table in enumerate(tables, start=1):
            # Reset table-level state (each Court block is independent)

            rows = table.find_all("tr")

            for row in rows:
                tr_global_index += 1
                # Collect column cells WITHOUT dropping empty ones (preserve column index)
                cols = []
                for cell in row.find_all(["th", "td"], recursive=False):
                    # If this cell contains nested <th> (Word-style headers), keep ONE placeholder
                    inner_ths = cell.find_all("th", recursive=True)
                    if inner_ths:
                        # Always append a single representative <th> to keep position
                        cols.append(inner_ths[0])
                    else:
                        # Always append the <td>, even if empty
                        cols.append(cell)

                # Robust text extraction for Word HTML (&nbsp;, nested spans)
                raw_texts = [td.get_text(strip=True) for td in cols]

                cols, raw_texts = normalize_row_by_court(
                    cols,
                    raw_texts,
                    item.get("value"),
                    header_found,
                )

                # Step 1: collect non-empty texts
                texts = [t for t in raw_texts if t]

                # Step 2: detect bilingual (EN+ZH) combined labels
                bilingual_keys = set()
                for t in texts:
                    if re.search(r"[A-Za-z]", t) and re.search(r"[\u4e00-\u9fff]", t):
                        bilingual_keys.add(re.sub(r"\s+", "", t))

                # Step 3: build final col_texts
                col_texts = []
                used = set()

                for t in texts:
                    # Skip empty / whitespace-only column text
                    if not t or not t.strip():
                        continue

                    norm = re.sub(r"\s+", "", t)

                    # If a bilingual label exists, drop pure EN / pure ZH versions
                    if norm not in bilingual_keys:
                        # check if this text is pure EN or pure ZH and covered by a bilingual one
                        for bk in bilingual_keys:
                            if norm in bk:
                                break
                        else:
                            if norm not in used:
                                used.add(norm)
                                col_texts.append(t)
                    else:
                        if norm not in used:
                            used.add(norm)
                            col_texts.append(t)

                row_text = " ".join(raw_texts)

                if is_need_find_court:
                    detect_info = detect_court_no_and_master_from_text(row_text)

                    if detect_info.get("court"):
                        new_court = detect_info["court"]
                        if new_court != prev_values.get("court"):
                            prev_values["court"] = new_court

                    if detect_info.get("master"):
                        new_master = detect_info["master"]
                        if new_master != prev_values.get("master"):
                            prev_values["master"] = new_master

                    if detect_info.get("presiding_officer"):
                        new_presiding_officer = detect_info["presiding_officer"]
                        if new_presiding_officer != prev_values.get(
                            "presiding_officer"
                        ):
                            prev_values["presiding_officer"] = new_presiding_officer

                if is_header_row(
                    col_texts, get_expected_col_count_by_court(item.get("value"))
                ):
                    column_map = resolve_column_conflicts(build_column_map(col_texts))
                    header_found = True
                    continue

                if should_skip_header_row(col_texts, item.get("value"), header_found):
                    continue

                # Read values that exist in this row
                row_values = {}

                for key in prev_values:
                    value = get_col(cols, column_map, key)

                    if not value:
                        continue

                    # Validate time format (skip invalid rows)
                    if key == "time" and not is_valid_session_time(value):
                        continue

                    row_values[key] = value

                # Merge row values into prev_values
                for key, value in row_values.items():
                    if (
                        key in PROTECTED_CONTEXT_KEYS
                        and is_need_find_court
                        and prev_values.get(key)
                    ):
                        continue
                    prev_values[key] = value

                # A valid case must have a case number OR a claim number
                if (
                    not prev_values.get("case_no")
                    and not prev_values.get("claim_no")
                    and not prev_values.get("suit_application_no")
                ):
                    continue

                # print(detected_info)
                case_info = build_case_info(
                    code=item["value"],
                    code_text=item["text"],
                    judges=prev_values["judges"],
                    time=prev_values["time"],
                    case_no=prev_values["case_no"],
                    parties=prev_values["parties"],
                    nature_text=prev_values["nature"],
                    representation=prev_values["representation"],
                    master=prev_values["master"],
                    court=prev_values["court"],
                    name_of_deceased=prev_values["name_of_deceased"],
                    presiding_officer=prev_values["presiding_officer"],
                    hearing=prev_values["hearing"],
                    claimant=prev_values["claimant"],
                    defendant_respondent=prev_values["defendant_respondent"],
                    coroner=prev_values["coroner"],
                    defendant=prev_values["defendant"],
                    claim_no=prev_values["claim_no"],
                    claim_nature=prev_values["claim_nature"],
                    suit_application_no=prev_values["suit_application_no"],
                )

                all_cases.append(case_info)

        print(f"CODE: {item.get('value')}, TOTAL CASES: {len(all_cases)}")
        return all_cases
    except Exception as e:
        print("ERROR in o14:", e)
        return []
