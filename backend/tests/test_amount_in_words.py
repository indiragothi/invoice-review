from decimal import Decimal as D

import pytest

from app.clients import CLIENTS_BY_ID
from app.normalisation.dates import parse_date
from app.normalisation.words import parse_amount_in_words
from app.schemas.documents import Invoice, LineItem, TaxLine
from app.schemas.issues import IssueCode, Severity
from app.validation.invoice import amount_issues

# ------------------------------------------------------------------ parser


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Rupees Nine Thousand Two Hundred Ninety Three Only", "9293"),
        ("Rupees One Lakh Fifteen Thousand Five Hundred Only", "115500"),
        ("Rupees One Lakh Forty One Thousand Three Hundred Sixty Four Only", "141364"),
        (
            "Rupees Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine",
            "123456789",
        ),
        ("Rupees One Crore Only", "10000000"),
        ("Rupees Zero Only", "0"),
        ("rupees seventy-five thousand six hundred seventy-two only", "75672"),
        ("INR One Hundred and Five Only", "105"),
        ("Rs. Fourty Thousand Only", "40000"),
        ("Rupees Two Lakhs Only", "200000"),
        ("Rupees Hundred Only", "100"),
        ("Rupees Nine Thousand and Thirty Four Paise Only", "9000.34"),
        ("Rupees Nine Thousand Eighty Six and Thirty Four Paise Only", "9086.34"),
        ("Rupees Nine Thousand Eighty Six and Paise Thirty Four Only", "9086.34"),
    ],
)
def test_parse_amount_in_words(text, want):
    assert parse_amount_in_words(text) == (None if want is None else D(want))


@pytest.mark.parametrize(
    "text",
    [None, "", "Only", "Rupees Only", "Rupees Nine Thousand Banana Only", "9,293"],
)
def test_text_that_is_not_an_amount_gives_none(text):
    assert parse_amount_in_words(text) is None


def test_paise_over_99_is_rejected():
    assert parse_amount_in_words("Rupees Five and Hundred Paise Only") is None


def test_result_is_decimal():
    assert isinstance(parse_amount_in_words("Rupees Five Only"), D)


# ------------------------------------------------------------------ rule

CLIENT = CLIENTS_BY_ID["C001"]


def inv(words, total="1180.00"):
    return Invoice(
        vendor_gstin="23QSSPM6142B1ZF",
        buyer_gstin=CLIENT.gstin,
        place_of_supply_code="23",
        invoice_date=parse_date("14-08-2026"),
        line_items=[LineItem(taxable_amount=D("1000.00"), hsn_sac="1", gst_rate=D("18"))],
        taxable_value=D("1000.00"),
        tax_lines=[
            TaxLine(head="CGST", rate=D("9"), amount=D("90.00")),
            TaxLine(head="SGST", rate=D("9"), amount=D("90.00")),
        ],
        total=D(total),
        amount_in_words=words,
    )


def codes(invoice):
    return [i.code for i in amount_issues(invoice, CLIENT)]


def test_matching_words_raise_nothing():
    assert codes(inv("Rupees One Thousand One Hundred Eighty Only")) == []


def test_different_words_are_a_warning_with_both_values():
    issues = amount_issues(inv("Rupees One Thousand Two Hundred Eighty Only"), CLIENT)
    assert [i.code for i in issues] == [IssueCode.AMOUNT_IN_WORDS_MISMATCH]
    assert issues[0].severity == Severity.WARNING
    assert issues[0].field == "amount_in_words"
    assert "1280" in issues[0].message and "1180.00" in issues[0].message


def test_lakh_and_crore_are_read_the_indian_way():
    # 1,18,000 is "One Lakh Eighteen Thousand", not "One Hundred Eighteen Thousand" misread.
    big = inv("Rupees One Lakh Eighteen Thousand Only", total="118000.00")
    big.taxable_value = D("100000.00")
    big.line_items = [LineItem(taxable_amount=D("100000.00"), hsn_sac="1", gst_rate=D("18"))]
    big.tax_lines = [
        TaxLine(head="CGST", rate=D("9"), amount=D("9000.00")),
        TaxLine(head="SGST", rate=D("9"), amount=D("9000.00")),
    ]
    assert codes(big) == []


def test_words_for_whole_rupees_match_a_total_with_paise_within_tolerance():
    # Taxable value is adjusted so only the words are in question.
    invoice = inv("Rupees One Thousand One Hundred Eighty Only", total="1180.34")
    assert IssueCode.AMOUNT_IN_WORDS_MISMATCH not in codes(invoice)


def test_unreadable_or_missing_words_are_not_judged():
    assert codes(inv(None)) == []
    assert codes(inv("Rupees Nine Thousand Banana Only")) == []


def test_missing_total_is_not_compared_with_the_words():
    invoice = inv("Rupees One Thousand Only")
    invoice.total = None
    assert IssueCode.AMOUNT_IN_WORDS_MISMATCH not in codes(invoice)
