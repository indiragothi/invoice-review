"""Date checks and the Indian financial year (1 April - 31 March). Pure: `today` is passed in.

These return facts. The invoice / receipt rules map them to issue codes:
missing -> MISSING_INVOICE_DATE, unreadable / future -> INVALID_DATE,
ambiguous -> AMBIGUOUS_DATE, old -> OLD_INVOICE (warning).
"""

import calendar
from datetime import date
from typing import Literal

from app.schemas.documents import NormalisedDate

DateProblem = Literal["missing", "unreadable", "future", "ambiguous", "old"]

OLD_AFTER_MONTHS = 12


def financial_year(on: date) -> str:
    """`date(2026, 8, 14)` -> `"2026-27"`; `date(2027, 3, 31)` -> `"2026-27"`."""
    start = on.year if on.month >= 4 else on.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def months_before(on: date, months: int) -> date:
    """The same day `months` earlier; the last day of the month if that day does not exist."""
    index = on.year * 12 + (on.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(on.day, calendar.monthrange(year, month)[1]))


def date_problems(parsed: NormalisedDate, today: date) -> list[DateProblem]:
    """What is wrong with this date, if anything.

    An ambiguous date is reported alone: until the reviewer settles day and month, "future" and
    "old" would be judged on a reading that may be wrong.
    """
    if parsed.raw is None or not parsed.raw.strip():
        return ["missing"]
    if parsed.value is None:
        return ["unreadable"]
    if parsed.ambiguous:
        return ["ambiguous"]
    if parsed.value > today:
        return ["future"]
    if parsed.value < months_before(today, OLD_AFTER_MONTHS):
        return ["old"]
    return []
