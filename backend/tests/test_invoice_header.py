from datetime import date

from app.clients import CLIENTS_BY_ID
from app.normalisation.dates import parse_date
from app.schemas.documents import Invoice
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, Severity
from app.validation.invoice import header_issues

CLIENT = CLIENTS_BY_ID["C001"]  # 23QXGPS4821K1ZU
TODAY = date(2026, 10, 31)
VENDOR_GSTIN = "23QSSPM6142B1ZF"
OTHER_CLIENT_GSTIN = CLIENTS_BY_ID["C003"].gstin


def good(**changes) -> Invoice:
    base = {
        "vendor_name": "Narmada Agro",
        "vendor_gstin": VENDOR_GSTIN,
        "buyer_gstin": CLIENT.gstin,
        "invoice_number": "INV/26-27/001",
        "invoice_date": parse_date("14-08-2026"),
        "total": 1000,
    }
    return Invoice(**{**base, **changes})


def codes(invoice, fields=None):
    return [i.code for i in header_issues(invoice, fields or {}, CLIENT, TODAY)]


def grounded(confidence=1.0):
    return GroundedField(raw="x", grounding="grounded", confidence=confidence)


def test_a_clean_invoice_has_no_issues():
    assert codes(good()) == []


def test_missing_vendor_name_is_blocking():
    issues = header_issues(good(vendor_name=None), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.MISSING_VENDOR_NAME]
    assert issues[0].severity == Severity.ERROR
    assert issues[0].field == "vendor_name"


def test_missing_invoice_number():
    assert codes(good(invoice_number=None)) == [IssueCode.MISSING_INVOICE_NUMBER]


def test_invoice_number_longer_than_16_is_only_a_warning():
    issues = header_issues(good(invoice_number="A" * 17), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.INVOICE_NUMBER_TOO_LONG]
    assert issues[0].severity == Severity.WARNING
    assert codes(good(invoice_number="A" * 16)) == []


def test_missing_total():
    assert codes(good(total=None)) == [IssueCode.MISSING_TOTAL]


def test_date_rules_are_wired_in():
    assert codes(good(invoice_date=parse_date(None))) == [IssueCode.MISSING_INVOICE_DATE]
    assert codes(good(invoice_date=parse_date("15-11-2026"))) == [IssueCode.INVALID_DATE]
    assert codes(good(invoice_date=parse_date("04/05/2026"))) == [IssueCode.AMBIGUOUS_DATE]
    assert codes(good(invoice_date=parse_date("01-01-2020"))) == [IssueCode.OLD_INVOICE]


def test_old_invoice_is_a_warning_not_blocking():
    issue = header_issues(good(invoice_date=parse_date("01-01-2020")), {}, CLIENT, TODAY)[0]
    assert issue.severity == Severity.WARNING


def test_missing_vendor_gstin():
    assert codes(good(vendor_gstin=None)) == [IssueCode.MISSING_VENDOR_GSTIN]


def test_invalid_vendor_gstin_carries_the_fix_suggestion():
    issues = header_issues(good(vendor_gstin="23QMRPW2963E1ZE"), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.INVALID_VENDOR_GSTIN]
    assert issues[0].severity == Severity.ERROR
    assert issues[0].suggestion == "23QMRPW2963E1Z7"
    assert "23QMRPW2963E1Z7" in issues[0].message


def test_invalid_vendor_gstin_without_a_fix_has_no_suggestion():
    issue = header_issues(good(vendor_gstin="23QSSPM6142B1"), {}, CLIENT, TODAY)[0]
    assert issue.code == IssueCode.INVALID_VENDOR_GSTIN
    assert issue.suggestion is None


def test_missing_buyer_gstin_is_a_warning():
    issues = header_issues(good(buyer_gstin=None), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.MISSING_BUYER_GSTIN]
    assert issues[0].severity == Severity.WARNING


def test_invalid_buyer_gstin():
    # The client's GSTIN with S read as 5: invalid, and the fix points back at the client.
    issues = header_issues(good(buyer_gstin="23QXGP54821K1ZU"), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.INVALID_BUYER_GSTIN]
    assert issues[0].suggestion == CLIENT.gstin


def test_buyer_who_is_not_the_client():
    issues = header_issues(good(buyer_gstin=OTHER_CLIENT_GSTIN), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.BUYER_NOT_CLIENT]
    assert issues[0].severity == Severity.ERROR


def test_an_invalid_buyer_gstin_is_not_also_reported_as_not_client():
    assert IssueCode.BUYER_NOT_CLIENT not in codes(good(buyer_gstin="23QXGP54821K1ZU"))


def test_reverse_charge_warning():
    issues = header_issues(good(reverse_charge=True), {}, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.REVERSE_CHARGE]
    assert issues[0].severity == Severity.WARNING


def test_ungrounded_required_field_is_blocking():
    fields = {"vendor_gstin": GroundedField(raw=VENDOR_GSTIN, grounding="ungrounded")}
    issues = header_issues(good(), fields, CLIENT, TODAY)
    assert [i.code for i in issues] == [IssueCode.UNGROUNDED_REQUIRED_FIELD]
    assert issues[0].field == "vendor_gstin"
    assert issues[0].severity == Severity.ERROR


def test_ungrounded_optional_field_is_ignored():
    fields = {"buyer_name": GroundedField(raw="x", grounding="ungrounded")}
    assert codes(good(), fields) == []


def test_low_confidence_required_field_is_a_warning():
    fields = {"invoice_number": grounded(0.79), "total": grounded(0.80)}
    issues = header_issues(good(), fields, CLIENT, TODAY)
    assert [(i.code, i.field) for i in issues] == [
        (IssueCode.LOW_CONFIDENCE_FIELD, "invoice_number")
    ]
    assert issues[0].severity == Severity.WARNING


def test_low_confidence_on_a_missing_or_ungrounded_field_is_not_repeated():
    fields = {"total": GroundedField(raw=None, grounding="missing", confidence=0.0)}
    assert codes(good(total=None), fields) == [IssueCode.MISSING_TOTAL]


def test_every_blocking_code_is_an_error_and_the_rest_warnings():
    from app.schemas.issues import BLOCKING_CODES, make_issue

    for code in IssueCode:
        severity = make_issue(code, "m").severity
        assert (severity == Severity.ERROR) == (code in BLOCKING_CODES)
