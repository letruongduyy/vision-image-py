from text_utils import normalize_text
from case_builder import build_case_info


def log_section(title: str, data=None):
    print("=" * 67)
    print(title.upper())
    if data is not None:
        print(data)
    print("=" * 67)
