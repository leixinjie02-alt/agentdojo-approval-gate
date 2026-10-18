import re
from datetime import date


MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january february march april may june july august "
            "september october november december"
        ).split(),
        start=1,
    )
}

DATE_PATTERN = (
    r"(?P<day>\d{4}-\d{2}-\d{2}|(?:"
    + "|".join(MONTHS)
    + r")\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"
)

REQUEST_PATTERN = re.compile(
    r"(?:How many appointments do I have|What appointments do I have|"
    r"Show(?: me)? my (?:calendar|appointments)|What is on my calendar)"
    r"\s+on\s+"
    + DATE_PATTERN
    + r"[?.]?"
    + r"(?:\s+Please give me a summary of the description for each appointment\.)?",
    re.IGNORECASE,
)


def calendar_query_day(task_description: str) -> str | None:
    """Extract a date only from a supported explicit calendar query."""
    match = REQUEST_PATTERN.fullmatch(task_description.strip())
    if match is None:
        return None

    raw_day = match.group("day")

    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
            return date.fromisoformat(raw_day).isoformat()

        normalized = re.sub(
            r"(\d)(?:st|nd|rd|th)\b",
            r"\1",
            raw_day,
            flags=re.IGNORECASE,
        )
        month, day, year = normalized.replace(",", "").split()
        return date(int(year), MONTHS[month.lower()], int(day)).isoformat()
    except (ValueError, KeyError):
        return None