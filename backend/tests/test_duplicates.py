from datetime import date
from decimal import Decimal as D

from app.clients import CLIENTS_BY_ID
from app.normalisation.dates import parse_date
from app.schemas.documents import Invoice, Receipt
from app.schemas.issues import IssueCode, Severity
from app.validation.duplicates import (
    InvoiceKey,
    ReceiptKey,
    duplicate_file_issue,
    invoice_duplicate_issue,
    invoice_key,
    receipt_duplicate_issue,
    receipt_key,
)
from app.validation.invoice import validate_invoice
from app.validation.receipt import validate_receipt

CLIENT = CLIENTS_BY_ID["C001"]
TODAY = date(2026, 10, 31)
GSTIN = "23QSSPM6142B1ZF"


def inv(**changes) -> Invoice:
    base = {
        "vendor_gstin": GSTIN,
        "invoice_number": "INV/26-27/001",
        "invoice_date": parse_date("14-08-2026"),
        "total": D("1000"),
    }
    return Invoice(**{**base, **changes})


def rcpt(**changes) -> Receipt:
    base = {
        "merchant_name": "Hotel Saffron",
        "receipt_date": parse_date("24-10-2026"),
        "total": D("1176.00"),
    }
    return Receipt(**{**base, **changes})


# ------------------------------------------------------------------ invoice key


def test_invoice_key_parts():
    key = invoice_key(inv())
    assert key == InvoiceKey(GSTIN, "inv2627001", "2026-27")


def test_case_and_punctuation_do_not_make_a_different_number():
    assert invoice_key(inv(invoice_number="inv-26-27-001")) == invoice_key(inv())
    assert invoice_key(inv(invoice_number=" INV 26/27/001 ")) == invoice_key(inv())


def test_leading_zeros_do_matter():
    assert invoice_key(inv(invoice_number="INV-001")) != invoice_key(inv(invoice_number="INV-1"))


def test_the_same_number_in_another_financial_year_is_not_a_duplicate():
    assert invoice_key(inv(invoice_date=parse_date("14-02-2027"))) == invoice_key(inv())
    assert invoice_key(inv(invoice_date=parse_date("14-04-2027"))) != invoice_key(inv())


def test_the_same_number_from_another_vendor_is_not_a_duplicate():
    other = inv(vendor_gstin="23QBWFG7451A1ZX")
    assert invoice_key(other) != invoice_key(inv())


def test_incomplete_or_unsettled_invoices_have_no_key():
    assert invoice_key(inv(vendor_gstin=None)) is None
    assert invoice_key(inv(invoice_number=None)) is None
    assert invoice_key(inv(invoice_number="---")) is None
    assert invoice_key(inv(invoice_date=parse_date(None))) is None
    assert invoice_key(inv(invoice_date=parse_date("31-02-2026"))) is None
    assert invoice_key(inv(invoice_date=parse_date("04/05/2026"))) is None  # ambiguous


# ------------------------------------------------------------------ invoice rule


def test_duplicate_invoice_is_blocking_and_names_the_other_document():
    existing = {"doc-7": invoice_key(inv(invoice_number="inv/26-27/001"))}
    issue = invoice_duplicate_issue(inv(), existing)
    assert issue is not None
    assert issue.code == IssueCode.DUPLICATE_INVOICE
    assert issue.severity == Severity.ERROR
    assert issue.field == "invoice_number"
    assert "doc-7" in issue.message and "2026-27" in issue.message


def test_the_first_matching_document_is_named_deterministically():
    key = invoice_key(inv())
    issue = invoice_duplicate_issue(inv(), {"doc-9": key, "doc-2": key})
    assert issue is not None and "doc-2" in issue.message


def test_no_existing_match_no_issue():
    other = invoice_key(inv(invoice_number="INV/26-27/002"))
    assert invoice_duplicate_issue(inv(), {"doc-1": other}) is None
    assert invoice_duplicate_issue(inv(), {}) is None


def test_an_invoice_without_a_key_never_matches():
    existing = {"doc-1": invoice_key(inv())}
    assert invoice_duplicate_issue(inv(vendor_gstin=None), existing) is None


def test_validate_invoice_adds_the_duplicate_issue():
    existing = {"doc-1": invoice_key(inv())}
    issues = validate_invoice(inv(), {}, CLIENT, TODAY, existing=existing)
    assert IssueCode.DUPLICATE_INVOICE in [i.code for i in issues]
    assert IssueCode.DUPLICATE_INVOICE not in [
        i.code for i in validate_invoice(inv(), {}, CLIENT, TODAY)
    ]


# ------------------------------------------------------------------ receipts


def test_receipt_key_parts():
    key = receipt_key(rcpt())
    assert key == ReceiptKey("hotelsaffron", date(2026, 10, 24), D("1176.00"))


def test_receipt_total_compares_by_value_not_by_spelling():
    assert receipt_key(rcpt(total=D("1176"))) == receipt_key(rcpt(total=D("1176.00")))
    assert receipt_key(rcpt(total=D("1176.50"))) != receipt_key(rcpt())


def test_receipt_merchant_case_and_spacing_do_not_matter():
    assert receipt_key(rcpt(merchant_name="HOTEL  SAFFRON")) == receipt_key(rcpt())


def test_incomplete_receipts_have_no_key():
    assert receipt_key(rcpt(merchant_name=None)) is None
    assert receipt_key(rcpt(receipt_date=parse_date(None))) is None
    assert receipt_key(rcpt(receipt_date=parse_date("04/05/2026"))) is None
    assert receipt_key(rcpt(total=None)) is None


def test_duplicate_receipt_is_blocking():
    existing = {"doc-3": receipt_key(rcpt())}
    issue = receipt_duplicate_issue(rcpt(), existing)
    assert issue is not None
    assert issue.code == IssueCode.DUPLICATE_RECEIPT
    assert issue.severity == Severity.ERROR
    assert "doc-3" in issue.message


def test_a_different_day_or_amount_is_not_a_duplicate_receipt():
    existing = {"doc-3": receipt_key(rcpt())}
    assert receipt_duplicate_issue(rcpt(receipt_date=parse_date("25-10-2026")), existing) is None
    assert receipt_duplicate_issue(rcpt(total=D("1177.00")), existing) is None


def test_validate_receipt_adds_the_duplicate_issue():
    existing = {"doc-3": receipt_key(rcpt())}
    issues = validate_receipt(rcpt(), {}, TODAY, existing=existing)
    assert IssueCode.DUPLICATE_RECEIPT in [i.code for i in issues]


# ------------------------------------------------------------------ text form (for one DB column)


def test_text_form_is_stable_and_distinguishes_kinds():
    assert invoice_key(inv()).text == f"invoice|{GSTIN}|inv2627001|2026-27"
    assert receipt_key(rcpt()).text == "receipt|hotelsaffron|2026-10-24|1176"
    assert receipt_key(rcpt(total=D("1176"))).text == receipt_key(rcpt()).text


def test_duplicate_file_warns_on_same_hash_only():
    issue = duplicate_file_issue("abc", {"abc": "doc-1", "def": "doc-2"})
    assert issue is not None
    assert issue.code == IssueCode.DUPLICATE_FILE
    assert issue.severity == Severity.WARNING
    assert "doc-1" in issue.message
    assert duplicate_file_issue("zzz", {"abc": "doc-1"}) is None
    assert duplicate_file_issue("abc", {}) is None
