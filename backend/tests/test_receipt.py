from datetime import date
from decimal import Decimal as D

from app.normalisation.dates import parse_date
from app.schemas.documents import LineItem, Receipt, TaxLine
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, Severity
from app.validation.receipt import validate_receipt

TODAY = date(2026, 10, 31)


def item(amount):
    return LineItem(description="x", taxable_amount=D(amount))


def tax(head, amount):
    return TaxLine(head=head, rate=D("2.5"), amount=D(amount))


def rcpt(**changes) -> Receipt:
    """Restaurant bill: 1120 + 28 CGST + 28 SGST = 1176."""
    base = {
        "merchant_name": "Hotel Saffron",
        "receipt_date": parse_date("24-10-2026"),
        "line_items": [item("1120.00")],
        "tax_lines": [tax("CGST", "28.00"), tax("SGST", "28.00")],
        "total": D("1176.00"),
    }
    return Receipt(**{**base, **changes})


def found(receipt, fields=None):
    return validate_receipt(receipt, fields or {}, TODAY)


def codes(receipt, fields=None):
    return [i.code for i in found(receipt, fields)]


def test_a_clean_receipt_has_no_issues():
    assert codes(rcpt()) == []


def test_a_fuel_slip_needs_no_invoice_number_buyer_or_gstin():
    slip = Receipt(
        merchant_name="Indore Fuels",
        receipt_date=parse_date("26-10-2026"),
        total=D("3925.00"),
        tax_lines=[TaxLine(head="CGST", rate=D("0"), amount=D("0"))],
    )
    assert codes(slip) == []


def test_missing_merchant_is_blocking():
    issues = found(rcpt(merchant_name=None))
    assert [i.code for i in issues] == [IssueCode.MISSING_MERCHANT]
    assert issues[0].severity == Severity.ERROR
    assert issues[0].field == "vendor_name"


def test_receipt_date_rules():
    assert codes(rcpt(receipt_date=parse_date(None))) == [IssueCode.MISSING_RECEIPT_DATE]
    assert codes(rcpt(receipt_date=parse_date("15-11-2026"))) == [IssueCode.INVALID_DATE]
    assert codes(rcpt(receipt_date=parse_date("04/05/2026"))) == [IssueCode.AMBIGUOUS_DATE]


def test_an_old_receipt_gets_no_old_warning():
    assert codes(rcpt(receipt_date=parse_date("01-01-2020"))) == []


def test_missing_total_is_blocking():
    assert codes(rcpt(total=None)) == [IssueCode.MISSING_TOTAL]


def test_line_items_plus_tax_must_match_the_total():
    issues = found(rcpt(total=D("1276.00")))
    assert [i.code for i in issues] == [IssueCode.LINE_ITEMS_SUM_MISMATCH]
    assert issues[0].severity == Severity.ERROR
    assert "1176.00" in issues[0].message and "1276.00" in issues[0].message


def test_round_off_and_tolerance_count():
    assert codes(rcpt(total=D("1175.70"), round_off=D("-0.30"))) == []
    assert codes(rcpt(total=D("1177.00"))) == []


def test_no_line_items_means_nothing_to_compare():
    assert codes(rcpt(line_items=[])) == []


def test_unreadable_tax_amount_is_not_judged():
    broken = TaxLine(head="SGST", rate=D("2.5"), amount=None)
    assert codes(rcpt(tax_lines=[tax("CGST", "28.00"), broken])) == []


def test_printed_gstin_must_be_valid_but_none_is_fine():
    assert codes(rcpt(vendor_gstin=None)) == []
    assert codes(rcpt(vendor_gstin="23QNFFS1408C1ZO")) == []
    bad = found(rcpt(vendor_gstin="23QNFFS1408C1ZX"))
    assert [i.code for i in bad] == [IssueCode.INVALID_VENDOR_GSTIN]
    assert bad[0].field == "vendor_gstin"


def test_no_tax_rows_is_a_warning_only():
    issues = found(rcpt(tax_lines=[], line_items=[], total=D("3925.00")))
    assert [i.code for i in issues] == [IssueCode.MISSING_TAX_BREAKUP]
    assert issues[0].severity == Severity.WARNING


def test_ungrounded_required_field_blocks_but_other_fields_are_ignored():
    fields = {
        "total": GroundedField(raw="1176.00", grounding="ungrounded"),
        "buyer_name": GroundedField(raw="x", grounding="ungrounded"),
    }
    issues = found(rcpt(), fields)
    assert [(i.code, i.field) for i in issues] == [(IssueCode.UNGROUNDED_REQUIRED_FIELD, "total")]


def test_a_printed_gstin_is_a_required_grounded_field():
    fields = {"vendor_gstin": GroundedField(raw="x", grounding="ungrounded")}
    assert codes(rcpt(vendor_gstin="23QNFFS1408C1ZO"), fields) == [
        IssueCode.UNGROUNDED_REQUIRED_FIELD
    ]
    assert codes(rcpt(), fields) == []


def test_low_confidence_is_a_warning():
    fields = {"vendor_name": GroundedField(raw="x", grounding="grounded", confidence=0.5)}
    issues = found(rcpt(), fields)
    assert [(i.code, i.severity) for i in issues] == [
        (IssueCode.LOW_CONFIDENCE_FIELD, Severity.WARNING)
    ]
