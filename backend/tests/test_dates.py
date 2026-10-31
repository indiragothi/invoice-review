from datetime import date

import pytest

from app.normalisation.dates import parse_date
from app.schemas.documents import NormalisedDate
from app.validation.dates import date_problems, financial_year, months_before

TODAY = date(2026, 10, 31)


@pytest.mark.parametrize(
    ("on", "want"),
    [
        (date(2026, 4, 1), "2026-27"),
        (date(2026, 8, 14), "2026-27"),
        (date(2027, 3, 31), "2026-27"),
        (date(2026, 3, 31), "2025-26"),
        (date(2026, 1, 1), "2025-26"),
        (date(2099, 4, 1), "2099-00"),
    ],
)
def test_financial_year(on, want):
    assert financial_year(on) == want


@pytest.mark.parametrize(
    ("on", "months", "want"),
    [
        (date(2026, 10, 31), 12, date(2025, 10, 31)),
        (date(2024, 2, 29), 12, date(2023, 2, 28)),  # no 29 Feb in 2023
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
        (date(2026, 1, 15), 2, date(2025, 11, 15)),
    ],
)
def test_months_before(on, months, want):
    assert months_before(on, months) == want


def problems(text):
    return date_problems(parse_date(text), TODAY)


def test_a_normal_recent_date_has_no_problem():
    assert problems("14-08-2026") == []


def test_today_is_not_in_the_future():
    assert problems("31-10-2026") == []


def test_a_later_date_is_in_the_future():
    assert problems("15-11-2026") == ["future"]
    assert problems("31-12-2030") == ["future"]


def test_a_day_ahead_is_in_the_future():
    assert date_problems(NormalisedDate(raw="x", value=date(2026, 11, 1)), TODAY) == ["future"]


def test_not_printed_is_missing():
    assert date_problems(NormalisedDate(), TODAY) == ["missing"]
    assert problems(None) == ["missing"]
    assert problems("   ") == ["missing"]


def test_printed_but_unparseable_is_unreadable():
    assert problems("sometime in May") == ["unreadable"]
    assert problems("31-02-2026") == ["unreadable"]


def test_ambiguous_is_reported_alone():
    # 04/05/2027 would be "future" on the day-first reading, but the reviewer must settle it first.
    assert problems("04/05/2027") == ["ambiguous"]
    assert problems("04/05/2026") == ["ambiguous"]


def test_older_than_twelve_months_is_old():
    assert problems("30-10-2025") == ["old"]
    assert problems("01-01-2020") == ["old"]


def test_exactly_twelve_months_ago_is_not_old():
    assert problems("31-10-2025") == []
