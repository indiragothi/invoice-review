from datetime import date
from decimal import Decimal

import pytest

from app.normalisation.amounts import parse_amount, parse_percent
from app.normalisation.dates import parse_date
from app.normalisation.states import state_code_from_gstin, state_code_from_text
from app.normalisation.text import clean_text, normalise_gstin

# ------------------------------------------------------------------ amounts


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("1,23,456.00", "123456.00"),
        ("₹ 1,10,000.00", "110000.00"),
        ("Rs. 75,672", "75672"),
        ("INR 500.50", "500.50"),
        ("-0.34", "-0.34"),
        ("(0.30)", "-0.30"),
        ("1,000/-", "1000"),
        ("0.00", "0.00"),
    ],
)
def test_parse_amount(text, want):
    assert parse_amount(text) == Decimal(want)


@pytest.mark.parametrize("text", [None, "", "abc", "1.2.3", "12 pcs", "--5"])
def test_parse_amount_rejects_non_numbers(text):
    assert parse_amount(text) is None


def test_amounts_are_decimal_not_float():
    assert isinstance(parse_amount("0.10"), Decimal)
    assert parse_amount("0.10") + parse_amount("0.20") == Decimal("0.30")


@pytest.mark.parametrize(
    ("text", "want"), [("9%", "9"), ("@ 2.5 %", "2.5"), ("18", "18"), ("CGST 9 %", "9")]
)
def test_parse_percent(text, want):
    assert parse_percent(text) == Decimal(want)


def test_parse_percent_none():
    assert parse_percent(None) is None
    assert parse_percent("nil") is None


# ------------------------------------------------------------------ dates


@pytest.mark.parametrize(
    "text",
    ["25-04-2025", "25/04/2025", "25.04.2025", "25 Apr 2025", "25-Apr-2025", "April 25, 2025"],
)
def test_unambiguous_dates(text):
    result = parse_date(text)
    assert result.value == date(2025, 4, 25)
    assert not result.ambiguous
    assert result.raw == text


def test_day_and_month_could_swap_is_ambiguous_and_day_first():
    result = parse_date("04/05/2025")
    assert result.ambiguous
    assert result.value == date(2025, 5, 4)  # day-first reading kept as the suggestion


def test_same_day_and_month_is_not_ambiguous():
    result = parse_date("05-05-2025")
    assert result.value == date(2025, 5, 5)
    assert not result.ambiguous


def test_month_name_is_never_ambiguous():
    assert not parse_date("04 May 2025").ambiguous
    assert parse_date("04 May 2025").value == date(2025, 5, 4)


def test_month_first_only_possible_reading_is_not_guessed_wrongly():
    result = parse_date("04/25/2025")
    assert result.value == date(2025, 4, 25)
    assert not result.ambiguous


def test_two_digit_year():
    assert parse_date("14-08-26").value == date(2026, 8, 14)


def test_impossible_date_has_no_value_but_keeps_raw():
    result = parse_date("31-02-2025")
    assert result.value is None
    assert result.raw == "31-02-2025"
    assert not result.ambiguous


def test_unparseable_date_has_raw_but_no_value():
    result = parse_date("sometime in May")
    assert result.raw == "sometime in May"
    assert result.value is None


def test_missing_date_has_no_raw():
    assert parse_date(None).raw is None
    assert parse_date("  ").value is None


# ------------------------------------------------------------------ text


def test_gstin_is_uppercased_and_unspaced():
    assert normalise_gstin(" 23qxgps4821k1zu ") == "23QXGPS4821K1ZU"
    assert normalise_gstin("23QXG PS4821 K1ZU") == "23QXGPS4821K1ZU"
    assert normalise_gstin("  ") is None
    assert normalise_gstin(None) is None


def test_clean_text():
    assert clean_text("  Shree   Ganesh \n Traders ") == "Shree Ganesh Traders"
    assert clean_text("   ") is None


# ------------------------------------------------------------------ states


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Karnataka", "29"),
        ("karnataka", "29"),
        ("Madhya Pradesh (23)", "23"),
        ("29-Karnataka", "29"),
        ("27", "27"),
        ("Dadra and Nagar Haveli and Daman and Diu", "26"),
        ("Daman & Diu", "26"),
        ("J&K", "01"),
        ("Orissa", "21"),
    ],
)
def test_state_code_from_text(text, want):
    assert state_code_from_text(text) == want


def test_conflicting_name_and_code_is_not_guessed():
    assert state_code_from_text("Karnataka (27)") is None


@pytest.mark.parametrize("text", [None, "", "Atlantis", "00", "98"])
def test_unknown_state_is_none(text):
    assert state_code_from_text(text) is None


def test_state_code_from_gstin():
    assert state_code_from_gstin("29QKDPK5274H1ZH") == "29"
    assert state_code_from_gstin("00ABCDE1234F1Z5") is None
    assert state_code_from_gstin(None) is None
