import re


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z0-9\s]", " ", text)
    return " ".join(text.split())
