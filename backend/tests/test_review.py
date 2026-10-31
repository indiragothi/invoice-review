from datetime import date
from decimal import Decimal as D

from app.clients import CLIENTS_BY_ID
from app.normalisation.dates import parse_date
from app.schemas.documents import Invoice, LineItem, Receipt, TaxLine
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, Severity, make_issue
from app.validation.duplicates import invoice_key
from app.validation.review import review_document, review_status, tidy_issues

CLIENT = CLIENTS_BY_ID["C001"]
TODAY = date(2026, 10, 31)
INVOICE_KEYS = ("vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "total")
RECEIPT_KEYS = ("vendor_name", "invoice_date", "total")


RAW = {"vendor_gstin": "23QSSPM6142B1ZF", "invoice_date": "14-08-2026", "total": "1,180.00"}


def good_fields(keys, confidence=1.0):
    """Grounded fields with realistic raw text (format caps look at the raw value)."""
    return {
        k: GroundedField(raw=RAW.get(k, "x"), grounding="grounded", confidence=confidence)
        for k in keys
    }


def invoice(**changes) -> Invoice:
    base = {
        "vendor_name": "Narmada Agro",
        "vendor_gstin": "23QSSPM6142B1ZF",
        "buyer_gstin": CLIENT.gstin,
        "invoice_number": "INV/26-27/001",
        "invoice_date": parse_date("14-08-2026"),
        "place_of_supply_code": "23",
        "line_items": [LineItem(taxable_amount=D("1000"), hsn_sac="1", gst_rate=D("18"))],
        "taxable_value": D("1000"),
        "tax_lines": [
            TaxLine(head="CGST", rate=D("9"), amount=D("90")),
            TaxLine(head="SGST", rate=D("9"), amount=D("90")),
        ],
        "total": D("1180"),
    }
    return Invoice(**{**base, **changes})


def receipt(**changes) -> Receipt:
    base = {
        "merchant_name": "Indore Fuels",
        "receipt_date": parse_date("26-10-2026"),
        "total": D("3925.00"),
        "tax_lines": [TaxLine(head="CGST", rate=D("0"), amount=D("0"))],
    }
    return Receipt(**{**base, **changes})


def review_invoice(doc=None, fields=None, **kwargs):
    return review_document(
        doc or invoice(), fields or good_fields(INVOICE_KEYS), CLIENT, TODAY, **kwargs
    )


# ------------------------------------------------------------------ status


def test_a_clean_invoice_is_ready():
    result = review_invoice()
    assert result.status == "ready"
    assert result.issues == []


def test_a_blocking_error_means_needs_review():
    result = review_invoice(invoice(total=D("1280")))
    assert result.status == "needs_review"
    assert [i.code for i in result.issues] == [IssueCode.TOTAL_MISMATCH]


def test_warnings_alone_keep_the_invoice_ready():
    result = review_invoice(invoice(buyer_gstin=None))  # B2C bill: warning only
    assert [i.code for i in result.issues] == [IssueCode.MISSING_BUYER_GSTIN]
    assert result.status == "ready"


def test_a_required_field_below_the_threshold_means_needs_review():
    result = review_invoice(fields=good_fields(INVOICE_KEYS, confidence=0.79))
    assert result.status == "needs_review"
    assert IssueCode.LOW_CONFIDENCE_FIELD in [i.code for i in result.issues]


def test_exactly_the_threshold_is_enough():
    assert review_invoice(fields=good_fields(INVOICE_KEYS, confidence=0.80)).status == "ready"


def test_an_ungrounded_or_absent_required_field_means_needs_review():
    fields = good_fields(INVOICE_KEYS)
    fields["total"] = GroundedField(raw="x", grounding="ungrounded")
    assert review_invoice(fields=fields).status == "needs_review"
    without_total = {k: v for k, v in good_fields(INVOICE_KEYS).items() if k != "total"}
    assert review_status([], without_total, INVOICE_KEYS) == "needs_review"


def test_a_low_confidence_optional_field_does_not_block():
    fields = good_fields(INVOICE_KEYS)
    fields["buyer_name"] = GroundedField(raw="x", grounding="grounded", confidence=0.1)
    assert review_invoice(fields=fields).status == "ready"


def test_duplicates_are_passed_through():
    existing = {"doc-1": invoice_key(invoice())}
    result = review_invoice(existing=existing)
    assert result.status == "needs_review"
    assert [i.code for i in result.issues] == [IssueCode.DUPLICATE_INVOICE]


# ------------------------------------------------------------------ receipts


def test_a_fuel_receipt_with_a_shaky_gstin_but_good_required_fields_is_ready():
    fields = good_fields(RECEIPT_KEYS, confidence=0.9)
    fields["vendor_gstin"] = GroundedField(
        raw="23QNFFS1408C1ZO", grounding="grounded", confidence=0.71
    )
    result = review_document(receipt(vendor_gstin="23QNFFS1408C1ZO"), fields, CLIENT, TODAY)
    assert result.status == "ready"
    assert result.issues == []


def test_a_receipt_needs_only_merchant_date_and_total():
    assert review_document(receipt(), good_fields(RECEIPT_KEYS), CLIENT, TODAY).status == "ready"
    low_total = good_fields(RECEIPT_KEYS)
    low_total["total"] = GroundedField(raw="3,925.00", grounding="grounded", confidence=0.5)
    assert review_document(receipt(), low_total, CLIENT, TODAY).status == "needs_review"


# ------------------------------------------------------------------ caps and tidy-up


def test_an_invalid_gstin_is_capped_and_reported_once():
    fields = good_fields(INVOICE_KEYS)
    fields["vendor_gstin"] = GroundedField(
        raw="23QMRPW2963E1ZE", grounding="grounded", confidence=1.0
    )
    result = review_invoice(invoice(vendor_gstin="23QMRPW2963E1ZE"), fields)
    assert result.fields["vendor_gstin"].confidence == 0.3
    assert fields["vendor_gstin"].confidence == 1.0  # the input is not changed
    on_gstin = [i for i in result.issues if i.field == "vendor_gstin"]
    assert [i.code for i in on_gstin] == [IssueCode.INVALID_VENDOR_GSTIN]
    assert result.status == "needs_review"


def test_a_low_confidence_warning_stays_when_the_field_has_no_error():
    result = review_invoice(fields=good_fields(INVOICE_KEYS, confidence=0.5))
    assert IssueCode.LOW_CONFIDENCE_FIELD in [i.code for i in result.issues]


def test_errors_are_listed_before_warnings():
    result = review_invoice(invoice(buyer_gstin=None, total=D("1280")))
    assert result.issues[0].severity == Severity.ERROR
    assert result.issues[-1].severity == Severity.WARNING


def test_tidy_issues_keeps_the_original_order_within_a_severity():
    a = make_issue(IssueCode.MISSING_BUYER_GSTIN, "a")
    b = make_issue(IssueCode.OLD_INVOICE, "b")
    c = make_issue(IssueCode.MISSING_TOTAL, "c")
    assert [i.message for i in tidy_issues([a, b, c])] == ["c", "a", "b"]
