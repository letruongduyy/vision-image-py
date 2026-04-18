from datetime import datetime
from text_utils import normalize_text


def build_case_info(
    code=None,
    code_text=None,
    judges=None,
    time=None,
    case_no=None,
    parties=None,
    nature_text=None,
    representation=None,
    master=None,
    court=None,
    name_of_deceased=None,
    presiding_officer=None,
    hearing=None,
    claimant=None,
    defendant_respondent=None,
    coroner=None,
    defendant=None,
    claim_no=None,
    claim_nature=None,
    suit_application_no=None,
):
    raw_search_text = ", ".join(
        filter(
            None,
            [
                court,
                judges,
                time,
                case_no,
                parties,
                nature_text,
                representation,
                master,
                name_of_deceased,
                presiding_officer,
                hearing,
                claimant,
                defendant_respondent,
                coroner,
                defendant,
                code_text,
                claim_no,
                claim_nature,
                suit_application_no,
            ],
        )
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "court": court or "",
        "judges": judges or "",
        "time": time or "",
        "caseNo": case_no or "",
        "parties": parties or "",
        "nature": nature_text or "",
        "representation": representation or "",
        # "searchText": normalize_text(raw_search_text),
        "searchText": raw_search_text,
        "createDate": now,
        "updateDate": now,
        "code": code,
        "codeText": normalize_text(code_text) or "",
        "master": master or "",
        "nameOfDeceased": name_of_deceased or "",
        "presidingOfficer": presiding_officer or "",
        "hearing": hearing or "",
        "claimant": claimant or "",
        "defendantRespondent": defendant_respondent or "",
        "coroner": coroner or "",
        "defendant": defendant or "",
        "claimNo": claim_no or "",
        "claimNature": claim_nature or "",
        "suitApplicationNo": suit_application_no or "",
    }
