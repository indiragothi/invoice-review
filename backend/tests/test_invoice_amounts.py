from datetime import date
from decimal import Decimal as D

from app.clients import CLIENTS_BY_ID
from app.normalisation.dates import parse_date
from app.schemas.documents import Invoice, LineItem, TaxLine
from app.schemas.issues import IssueCode, Severity
from app.validation.invoice import amount_issues, validate_invoice

CLIENT = CLIENTS_BY_ID["C001"]  # state 23
TODAY = date(2026, 10, 31)


def line(amount="1000.00", hsn="998719", rate="18"):
    return LineItem(taxable_amount=D(amount), hsn_sac=hsn, gst_rate=D(rate))


def tax_line(head, amount, rate="9"):
    return TaxLine(head=head, rate=D(rate), amount=D(amount))


def inv(**changes) -> Invoice:
    """Intra-state invoice: 1000 + 90 CGST + 90 SGST = 1180."""
    base = {
        "vendor_gstin": "23QSSPM6142B1ZF",
        "buyer_gstin": CLIENT.gstin,
        "place_of_supply_code": "23",
        "invoice_date": parse_date("14-08-2026"),
        "line_items": [line()],
        "taxable_value": D("1000.00"),
        "tax_lines": [tax_line("CGST", "90.00"), tax_line("SGST", "90.00")],
        "total": D("1180.00"),
    }
    return Invoice(**{**base, **changes})


def codes(invoice):
    return [i.code for i in amount_issues(invoice, CLIENT)]


def test_consistent_invoice_has_no_amount_issues():
    assert codes(inv()) == []


def test_total_mismatch_is_blocking_with_the_numbers():
    issues = amount_issues(inv(total=D("1280.00")), CLIENT)
    assert [i.code for i in issues] == [IssueCode.TOTAL_MISMATCH]
    assert issues[0].severity == Severity.ERROR
    assert issues[0].field == "total"
    assert "1180.00" in issues[0].message and "1280.00" in issues[0].message


def test_total_within_one_rupee_is_fine_and_round_off_counts():
    assert codes(inv(total=D("1181.00"))) == []
    assert codes(inv(total=D("1179.66"), round_off=D("-0.34"))) == []
    assert codes(inv(total=D("1181.50"))) == [IssueCode.TOTAL_MISMATCH]


def test_cess_is_part_of_the_total():
    cess = tax_line("CESS", "20.00", "1")
    assert codes(inv(tax_lines=inv().tax_lines + [cess], total=D("1200.00"))) == []


def test_no_split_or_total_judgement_when_a_tax_amount_is_unreadable():
    broken = TaxLine(head="SGST", rate=D("9"), amount=None)
    assert codes(inv(tax_lines=[tax_line("CGST", "90.00"), broken])) == []


def test_missing_total_or_taxable_value_is_not_a_mismatch():
    assert IssueCode.TOTAL_MISMATCH not in codes(inv(total=None))
    assert IssueCode.TOTAL_MISMATCH not in codes(inv(taxable_value=None))


def test_line_items_sum_mismatch():
    issues = amount_issues(inv(line_items=[line("400.00"), line("500.00")]), CLIENT)
    assert [i.code for i in issues] == [IssueCode.LINE_ITEMS_SUM_MISMATCH]
    assert issues[0].severity == Severity.ERROR
    assert "900.00" in issues[0].message


def test_line_items_sum_within_tolerance():
    assert codes(inv(line_items=[line("400.50"), line("599.50")])) == []


def test_no_line_items_is_not_a_sum_mismatch():
    assert codes(inv(line_items=[])) == []


def test_igst_on_a_same_state_supply():
    wrong = inv(tax_lines=[tax_line("IGST", "180.00", "18")])
    assert codes(wrong) == [IssueCode.TAX_SPLIT_INCONSISTENT]


def test_cgst_sgst_on_an_other_state_supply():
    other_state = inv(place_of_supply_code="29")
    assert codes(other_state) == [IssueCode.TAX_SPLIT_INCONSISTENT]


def test_correct_inter_state_invoice():
    ok = inv(place_of_supply_code="29", tax_lines=[tax_line("IGST", "180.00", "18")])
    assert codes(ok) == []


def test_unequal_cgst_and_sgst():
    uneven = inv(
        tax_lines=[tax_line("CGST", "100.00"), tax_line("SGST", "80.00")],
        total=D("1180.00"),
    )
    assert IssueCode.TAX_SPLIT_INCONSISTENT in codes(uneven)


def test_split_is_not_judged_when_supply_type_is_unknown():
    unknown = inv(vendor_gstin=None, tax_lines=[tax_line("IGST", "180.00", "18")])
    assert IssueCode.TAX_SPLIT_INCONSISTENT not in codes(unknown)


def test_missing_hsn_names_the_line():
    issues = amount_issues(
        inv(line_items=[line(), line(hsn=None)], taxable_value=D("2000")), CLIENT
    )
    hsn = [i for i in issues if i.code == IssueCode.MISSING_HSN_SAC]
    assert [i.field for i in hsn] == ["line_items[1].hsn_sac"]
    assert hsn[0].severity == Severity.WARNING


def test_unusual_rate_depends_on_the_invoice_date():
    twelve = line(rate="12")
    after = inv(line_items=[twelve])  # 14-08-2026: 12 % was abolished on 22-09-2025
    before = inv(line_items=[twelve], invoice_date=parse_date("14-08-2025"))
    assert IssueCode.UNUSUAL_TAX_RATE in codes(after)
    assert IssueCode.UNUSUAL_TAX_RATE not in codes(before)
    issue = [i for i in amount_issues(after, CLIENT) if i.code == IssueCode.UNUSUAL_TAX_RATE][0]
    assert issue.field == "line_items[0].gst_rate"
    assert issue.severity == Severity.WARNING


def test_no_rate_check_without_a_rate_or_a_date():
    assert IssueCode.UNUSUAL_TAX_RATE not in codes(
        inv(line_items=[LineItem(hsn_sac="1", taxable_amount=D("1000"))])
    )
    assert IssueCode.UNUSUAL_TAX_RATE not in codes(
        inv(line_items=[line(rate="7")], invoice_date=parse_date("x"))
    )


def test_validate_invoice_joins_header_and_amount_rules():
    broken = inv(vendor_name=None, total=D("1280.00"))
    found = {i.code for i in validate_invoice(broken, {}, CLIENT, TODAY)}
    assert {IssueCode.MISSING_VENDOR_NAME, IssueCode.MISSING_INVOICE_NUMBER} <= found
    assert IssueCode.TOTAL_MISMATCH in found
