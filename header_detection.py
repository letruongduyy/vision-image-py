import re

COLUMN_LABELS = {
    "court": ["法庭", "Court"],
    "judges": ["法官", "Judges", "Judge", "Judges / Members", "法官/審裁處成員"],
    "master": ["聆案官", "Master"],
    "coroner": ["死因裁判官", "Coroner"],
    "time": ["時間", "Time"],
    "case_no": [
        "案件編號",
        "Case No",
        "Case No.",
    ],
    "parties": ["訴訟各方", "Parties"],
    "nature": ["性質", "控罪", "控罪/性質", "Nature", "Offence/Nature", "控罪/性質"],
    "representation": ["應訊代表", "Representation"],
    "name_of_deceased": ["Name of Deceased", "死者姓名"],
    "claim_no": ["Claim No", "Claim No.", "申索編號"],
    "hearing": ["Hearing", "聆訊"],
    "claimant": ["Claimant", "申索人"],
    "defendant_respondent": ["被告/ 答辯人", "Defendant/ Respondent"],
    "presiding_officer": ["Presiding Officers/ Members", "法官/審裁處成員"],
    "defendant": ["被告人", "Defendant"],
    "claim_nature": ["Claim Nature", "申索性質"],
    "suit_application_no": ["Suit / Application No", "案件號碼"],
}


def is_header_row(col_texts, count):
    # Reject obvious data rows
    joined = " ".join(col_texts)
    if re.search(r"\d{2,}", joined):
        return False

    hits = 0
    for text in col_texts:
        normalized_text = re.sub(r"\s+", "", text)
        for labels in COLUMN_LABELS.values():
            for label in labels:
                normalized_label = re.sub(r"\s+", "", label)
                if normalized_label in normalized_text:
                    hits += 1
                    break

    return hits >= count


def get_presiding_officer_from_cols(col_texts):
    """
    Extract presiding officer text from column texts.
    Preference order:
    1. Chinese presiding officer (審裁官 / 裁判官)
    2. English presiding officer / adjudicator / magistrate
    """

    chi_candidate = ""
    eng_candidate = ""

    for text in col_texts:
        if not text:
            continue

        t = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

        # Chinese: 審裁官 / 暫委審裁官 / 裁判官 / 主任裁判官
        if re.search(r"(審裁官|裁判官)", t):
            chi_candidate = t
            continue

        # English: Presiding Officer / Adjudicator / Magistrate
        m = re.search(
            r"(Mr|Ms|Mrs)\.?\s+.+?,\s*"
            r"(Presiding Officer|Deputy Adjudicator|Adjudicator|Principal Magistrate|Magistrate)",
            t,
            re.IGNORECASE,
        )
        if m:
            eng_candidate = m.group(0)

    # Prefer Chinese if available
    if chi_candidate:
        return chi_candidate

    return eng_candidate


def get_court_no_from_cols(col_texts):
    """
    Extract and merge full court text (Chinese + English) into ONE string.
    Example return:
    "第23法庭 (西九龍法院大樓B座 4 字樓) / Court No. 23 (4/F, Tower B, West Kowloon Law Courts Building)"
    """
    zh = ""
    en = ""

    for text in col_texts:
        if not text:
            continue

        # Chinese formats:
        # - 第23法庭
        # - 第  1庭（1樓）
        if re.search(r"第\s*\d+\s*(法庭|庭)", text):
            zh = text.strip().replace("\xa0", " ")

        # English format: Court No. 23
        if re.search(r"Court\s*No\.?\s*\d+", text, re.IGNORECASE):
            en = text.strip().replace("\xa0", " ")

    if zh and en:
        return f"{zh} / {en}"
    if zh:
        return zh
    if en:
        return en

    return ""


def detect_magistrate_from_text(text):
    """
    Extract magistrate display text.

    Example input:
    裁判官 Magistrate : 張志偉主任裁判官 Mr. David CHEUNG Chi-wai, Principal Magistrate

    Output:
    張志偉主任裁判官 Mr. David CHEUNG Chi-wai, Principal Magistrate
    """
    if not text:
        return ""

    t = text.replace("\xa0", " ").strip()

    if not re.search(r"裁判官\s*Magistrate", t):
        return ""

    # Split on colon and return the right-hand side
    parts = re.split(r"\s*:\s*", t, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()

    return ""


def detect_court_from_text(text):
    """
    Extract court display text.

    Example input:
    法庭 Court : 第一庭 六樓  No.1 (6/F)  新案件 Fresh Cases

    Output:
    第一庭 六樓  No.1 (6/F)  新案件 Fresh Cases
    """
    if not text:
        return ""

    t = text.replace("\xa0", " ").strip()

    if not re.search(r"法庭\s*Court", t):
        return ""

    # Split on colon and return the right-hand side
    parts = re.split(r"\s*:\s*", t, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()

    return ""


# --- Helper: extract Court and Judge from a mixed-format line ---
def detect_court_and_judge_from_text(text):
    """
    Extract Court and Judge from a mixed / inline text block.

    Example input:
    第1庭(1字樓)Court : Court No. 1 (1/F)
    法官:龍軍庭聆案官Judge : Master G.T. LUNG
    日期: 2025年12月24日(星期三)Date : Wednesday, 24th December 2025

    Returns:
    {
        "court": "第1庭(1字樓) Court No. 1 (1/F)",
        "judge": "龍軍庭聆案官 Master G.T. LUNG"
    }
    """
    if not text:
        return {"court": "", "judge": ""}

    t = text.replace("\xa0", " ").strip()

    court = ""
    judge = ""

    # -------- Court detection --------
    # Chinese court: 第1庭 / 第23法庭 (+ optional floor)
    m_zh = re.search(r"(第\s*\d+\s*(?:法庭|庭)(?:\s*\([^)]+\))?)", t)
    if m_zh:
        court_zh = m_zh.group(1).strip()
    else:
        court_zh = ""

    # English court: Court No. 1 (1/F)
    m_en = re.search(
        r"(Court\s*No\.?\s*\d+\s*\([^)]+\))",
        t,
        re.IGNORECASE,
    )
    if m_en:
        court_en = m_en.group(1).strip()
    else:
        court_en = ""

    if court_zh and court_en:
        court = f"{court_zh} {court_en}"
    elif court_zh:
        court = court_zh
    elif court_en:
        court = court_en

    # -------- Judge detection --------
    # Chinese judge titles: 聆案官 / 法官 / 裁判官
    m_judge_zh = re.search(
        r"(?:法官|裁判官)[:：]?\s*([^\sA-Za-z]+?(?:聆案官|裁判官|法官))",
        t,
    )
    if m_judge_zh:
        judge_zh = m_judge_zh.group(1).strip()
    else:
        judge_zh = ""

    # English judge: Judge : Master G.T. LUNG
    m_judge_en = re.search(
        r"(Judge|Magistrate)\s*:\s*([A-Za-z .]+)",
        t,
        re.IGNORECASE,
    )
    if m_judge_en:
        judge_en = m_judge_en.group(2).strip()
    else:
        judge_en = ""

    if judge_zh and judge_en:
        judge = f"{judge_zh} {judge_en}"
    elif judge_zh:
        judge = judge_zh
    elif judge_en:
        judge = judge_en

    return {
        "court": court,
        "judge": judge,
    }


def extract_court_from_rows(rows):
    try:
        court_parts = []

        for i, row in enumerate(rows, start=1):
            row_text = row.get_text(" ", strip=True)
            if detect_court_no_and_master_from_text(row_text).get("court"):
                court_parts.append(
                    detect_court_no_and_master_from_text(row_text).get("court")
                )

        return re.sub(r"\s+", " ", " ".join(court_parts)).strip()

    except Exception:
        # absolute fail-safe
        return ""


def detect_court_no_and_master_from_text(text):
    """
    Extract Court No and Master from a mixed / inline text block.

    Example input:
    法庭:第37庭Court No.: No. 37 聆案官:廖玉玲聆案官Master : Master Elaine Liu

    Returns:
    {
        "court": "第37庭 Court No. 37",
        "master": "廖玉玲聆案官 Master Elaine Liu",
        "presiding_officer": "張志偉主任裁判官"
    }
    """
    if not text:
        return {"court": "", "master": "", "presiding_officer": ""}

    t = text.replace("\xa0", " ").strip()

    court = ""
    master = ""
    presiding_officer = ""

    # --- Special case: 法庭 Court : 第一庭 六樓  No.1 (6/F)  新案件 Fresh Cases ---
    if re.search(r"法庭\s*Court\s*:", t):
        parts = re.split(r"\s*:\s*", t, maxsplit=1)
        if len(parts) == 2:
            # Keep FULL plaintext (court + floor + group)
            body = parts[1].strip()
            court = body

    # -------- Court detection --------
    # Chinese court: 第37庭 / 第37法庭
    m_zh = re.search(r"(第\s*\d+\s*(?:庭|法庭))", t)
    court_zh = m_zh.group(1).strip() if m_zh else ""

    # English court: Court No.: No. 37 / Court No. 37
    m_en = re.search(
        r"Court\s*No\.?\s*:?\s*(?:No\.?\s*)?(\d+)",
        t,
        re.IGNORECASE,
    )
    court_en = f"Court No. {m_en.group(1)}" if m_en else ""

    if not court:
        if court_zh and court_en:
            court = f"{court_zh} {court_en}"
        elif court_zh:
            court = court_zh
        elif court_en:
            court = court_en

    # -------- Master detection --------
    # Chinese master name: 廖玉玲聆案官
    m_master_zh = re.search(r"聆案官[:：]?\s*([^\sA-Za-z]+?聆案官)", t)
    master_zh = m_master_zh.group(1).strip() if m_master_zh else ""

    # English master: Master : Master Elaine Liu
    m_master_en = re.search(
        r"Master\s*:\s*(Master\s+[A-Za-z .]+)",
        t,
        re.IGNORECASE,
    )
    master_en = m_master_en.group(1).strip() if m_master_en else ""

    if master_zh and master_en:
        master = f"{master_zh} {master_en}"
    elif master_zh:
        master = master_zh
    elif master_en:
        master = master_en

    # -------- Presiding Officer detection (merged from get_presiding_officer_from_cols) --------
    # Normalize whitespace
    t_norm = re.sub(r"\s+", " ", t)

    # Chinese presiding officer: 審裁官 / 裁判官 / 主任裁判官
    m_preside_zh = re.search(r"([^\sA-Za-z]+?(?:審裁官|裁判官))", t_norm)
    preside_zh = m_preside_zh.group(1).strip() if m_preside_zh else ""

    # English presiding officer: Adjudicator / Magistrate
    m_preside_en = re.search(
        r"(Mr|Ms|Mrs)\.?\s+.+?,\s*"
        r"(Presiding Officer|Deputy Adjudicator|Adjudicator|Principal Magistrate|Magistrate)",
        t_norm,
        re.IGNORECASE,
    )
    preside_en = m_preside_en.group(0).strip() if m_preside_en else ""

    # Prefer Chinese + English combined when both exist
    if preside_zh and preside_en:
        presiding_officer = f"{preside_zh} {preside_en}"
    elif preside_zh:
        presiding_officer = preside_zh
    elif preside_en:
        presiding_officer = preside_en

    return {
        "court": court,
        "master": master,
        "presiding_officer": presiding_officer,
    }


def build_column_map(col_texts):
    """
    Build column_map using REAL column indexes.
    - Keeps empty columns
    - No merging
    - No filtering
    - Index always matches cols[idx]
    """
    column_map = {}

    for idx, text in enumerate(col_texts):
        if not text:
            continue

        normalized_text = re.sub(r"\s+", "", text)

        for key, labels in COLUMN_LABELS.items():
            # Do not overwrite once mapped
            if key in column_map:
                continue

            for label in labels:
                normalized_label = re.sub(r"\s+", "", label)

                if normalized_label and normalized_label in normalized_text:
                    column_map[key] = idx
                    break

    return column_map


def resolve_column_conflicts(column_map):
    """
    Resolve conflicts where multiple keys map to the same column index.
    Keep the more specific key based on COLUMN_LABELS (longer label wins).
    """
    # Work on a copy of keys to avoid runtime modification issues
    keys = list(column_map.keys())

    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1 :]:
            if k1 not in column_map or k2 not in column_map:
                continue

            if column_map[k1] != column_map[k2]:
                continue

            labels1 = COLUMN_LABELS.get(k1, [])
            labels2 = COLUMN_LABELS.get(k2, [])

            max_len_1 = max((len(l) for l in labels1), default=0)
            max_len_2 = max((len(l) for l in labels2), default=0)

            # Drop the less specific key
            if max_len_1 > max_len_2:
                column_map.pop(k2, None)
            elif max_len_2 > max_len_1:
                column_map.pop(k1, None)

    return column_map


def merge_bilingual_col_texts(col_texts):
    merged = []
    used = [False] * len(col_texts)

    for i, text in enumerate(col_texts):
        if not text or used[i]:
            continue

        norm = re.sub(r"\s+", "", text)
        pair = [text]
        used[i] = True

        for labels in COLUMN_LABELS.values():
            labels_norm = [re.sub(r"\s+", "", l) for l in labels]
            if any(l in norm for l in labels_norm):
                for j in range(i + 1, len(col_texts)):
                    if used[j]:
                        continue
                    other = col_texts[j]
                    other_norm = re.sub(r"\s+", "", other)
                    if any(l in other_norm for l in labels_norm):
                        pair.append(other)
                        used[j] = True
                        break
                break

        merged.append(" ".join(pair))

    return merged


def get_col(cols, column_map, key):
    idx = column_map.get(key)
    if idx is None or idx >= len(cols):
        return ""
    return cols[idx].get_text("", strip=True)


def is_valid_session_time(text):
    """
    Accept formats:
    上午\n09:30 am
    下午\n02:30 pm
    上午\n09:30 a.m.
    下午\n04:30 p.m.
    """
    if not text:
        return False

    normalized = re.sub(r"\s+", " ", text.strip())

    return bool(
        re.search(
            r"(上午|下午)\s*\d{1,2}:\d{2}\s*(a\.?m\.?|p\.?m\.?)",
            normalized,
            re.IGNORECASE,
        )
    )
