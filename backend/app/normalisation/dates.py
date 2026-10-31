"""Printed dates to `NormalisedDate`. Indian bills are day-first (DD-MM-YYYY).

A numeric date where day and month could be swapped (04/05/2025) is never guessed: it is
flagged `ambiguous`, and `value` holds the day-first reading. Dates with a month name are never
ambiguous.
"""

import re
from datetime import date

from app.schemas.documents import NormalisedDate

_MONTH_NAMES = [
    ("jan", "january"),
    ("feb", "february"),
    ("mar", "march"),
    ("apr", "april"),
    ("may",),
    ("jun", "june"),
    ("jul", "july"),
    ("aug", "august"),
    ("sep", "sept", "september"),
    ("oct", "october"),
    ("nov", "november"),
    ("dec", "december"),
]
_MONTHS = {name: number for number, names in enumerate(_MONTH_NAMES, 1) for name in names}

_NUMERIC = re.compile(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4}|\d{2})")
_DAY_MONTH_NAME = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([A-Za-z]{3,9})[\s\-/.,]*(\d{4}|\d{2})"
)
_MONTH_NAME_DAY = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")


def _year(text: str) -> int:
    return int(text) if len(text) == 4 else 2000 + int(text)


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(text: str | None) -> NormalisedDate:
    if text is None or not text.strip():
        return NormalisedDate(raw=text)
    raw, cleaned = text, text.strip()

    if match := _NUMERIC.fullmatch(cleaned):
        first, second, year = int(match[1]), int(match[2]), _year(match[3])
        if second > 12 and first <= 12:
            # Month-first is the only possible reading, so nothing is being guessed.
            return NormalisedDate(raw=raw, value=_make(year, first, second))
        value = _make(year, second, first)
        ambiguous = value is not None and first <= 12 and first != second
        return NormalisedDate(raw=raw, value=value, ambiguous=ambiguous)

    if match := _DAY_MONTH_NAME.fullmatch(cleaned):
        month = _MONTHS.get(match[2].casefold())
        if month:
            return NormalisedDate(raw=raw, value=_make(_year(match[3]), month, int(match[1])))

    if match := _MONTH_NAME_DAY.fullmatch(cleaned):
        month = _MONTHS.get(match[1].casefold())
        if month:
            return NormalisedDate(raw=raw, value=_make(int(match[3]), month, int(match[2])))

    return NormalisedDate(raw=raw)
