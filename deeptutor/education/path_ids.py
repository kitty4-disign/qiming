import re


def build_mastery_path_id(textbook_id: str, course_id: str) -> str:
    raw = f"edu_{textbook_id}_{course_id}".lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
