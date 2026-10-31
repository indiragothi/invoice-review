from datetime import date
from decimal import Decimal as D

import pytest

from app.schemas.documents import LineItem, TaxLine
from app.validation.tax import (
    TaxTotals,
    differs,
    invoice_computed_total,
    line_items_sum,
    receipt_computed_total,
    supply_type,
    tax_split_problem,
    tax_totals,
)
from app.validation.tax_slabs import is_valid_slab, slabs_on

MP_VENDOR = "23QSSPM6142B1ZF"  # Madhya Pradesh (23)
MH_BUYER = "27QWRCA7310M1ZK"  # Maharashtra (27)


# ------------------------------------------------------------------ supply type


def test_vendor_state_equals_place_of_supply_is_intra():
    assert supply_type(MP_VENDOR, "23", None, None) == "intra"


def test_different_place_of_supply_is_inter():
    assert supply_type(MP_VENDOR, "29", None, None) == "inter"


def test_place_of_supply_beats_buyer_and_client():
    assert supply_type(MP_VENDOR, "23", MH_BUYER, "27") == "intra"


def test_without_place_of_supply_buyer_gstin_state_is_used():
    assert supply_type(MP_VENDOR, None, MH_BUYER, "23") == "inter"


def test_without_place_or_buyer_the_client_state_is_used():
    assert supply_type(MP_VENDOR, None, None, "23") == "intra"
    assert supply_type(MP_VENDOR, None, None, "29") == "inter"


@pytest.mark.parametrize("vendor", [None, "", "00ABCDE1234F1Z5"])
def test_unknown_vendor_state_gives_no_answer(vendor):
    assert supply_type(vendor, "23", None, None) is None


def test_no_destination_gives_no_answer():
    assert supply_type(MP_VENDOR, None, None, None) is None


# ------------------------------------------------------------------ tax totals


def line(head, amount, rate="9"):
    return TaxLine(head=head, rate=D(rate), amount=None if amount is None else D(amount))


def test_several_rows_per_head_are_added():
    totals = tax_totals(
        [line("CGST", "1409.85", "2.5"), line("SGST", "1409.85", "2.5"), line("CGST", "100.10")]
    )
    assert totals.cgst == D("1509.95")
    assert totals.sgst == D("1409.85")
    assert not totals.unreadable
    assert totals.total == D("2919.80")


def test_unreadable_amount_is_flagged_not_silently_zero():
    totals = tax_totals([line("CGST", "10"), line("SGST", None)])
    assert totals.unreadable
    assert totals.cgst == D("10")


def test_no_tax_rows():
    totals = tax_totals([])
    assert totals == TaxTotals()
    assert not totals.any_tax


# ------------------------------------------------------------------ tax split


def totals(cgst="0", sgst="0", igst="0", utgst="0", cess="0"):
    return TaxTotals(D(cgst), D(sgst), D(utgst), D(igst), D(cess))


def test_correct_intra_split():
    assert tax_split_problem("intra", totals(cgst="90", sgst="90")) is None


def test_intra_with_igst_is_a_problem():
    assert tax_split_problem("intra", totals(igst="233.82")) == "igst_on_intra"


def test_intra_cgst_sgst_must_be_equal_within_tolerance():
    assert tax_split_problem("intra", totals(cgst="90.00", sgst="90.99")) is None
    assert tax_split_problem("intra", totals(cgst="90.00", sgst="92.00")) == "cgst_sgst_unequal"


def test_union_territory_tax_counts_as_the_state_side():
    assert tax_split_problem("intra", totals(cgst="90", utgst="90")) is None


def test_correct_inter_split():
    assert tax_split_problem("inter", totals(igst="180")) is None


def test_inter_with_cgst_or_sgst_is_a_problem():
    assert tax_split_problem("inter", totals(cgst="90", sgst="90")) == "state_tax_on_inter"
    assert tax_split_problem("inter", totals(utgst="90")) == "state_tax_on_inter"


def test_no_tax_at_all_is_not_a_split_problem():
    assert tax_split_problem("intra", totals()) is None
    assert tax_split_problem("inter", totals()) is None


# ------------------------------------------------------------------ sums


def item(amount):
    return LineItem(taxable_amount=None if amount is None else D(amount))


def test_line_items_sum():
    assert line_items_sum([item("4500.00"), item("3200.00")]) == D("7700.00")


def test_line_items_sum_is_none_when_not_comparable():
    assert line_items_sum([]) is None
    assert line_items_sum([item("10"), item(None)]) is None


def test_invoice_computed_total_includes_tax_cess_and_round_off():
    t = totals(cgst="693", sgst="693", cess="5")
    assert invoice_computed_total(D("7700"), t, D("-0.34")) == D("9090.66")
    assert invoice_computed_total(D("7700"), t, None) == D("9091.00")
    assert invoice_computed_total(None, t, None) is None


def test_receipt_computed_total():
    t = totals(cgst="28", sgst="28")
    assert receipt_computed_total([item("1120")], t, None) == D("1176")
    assert receipt_computed_total([], t, None) is None


def test_difference_at_exactly_the_tolerance_is_fine():
    assert not differs(D("100.00"), D("101.00"))
    assert not differs(D("101.00"), D("100.00"))
    assert differs(D("100.00"), D("101.01"))


def test_money_is_exact_decimal():
    assert not differs(D("0.1") + D("0.2"), D("0.3"), tolerance=D("0"))


# ------------------------------------------------------------------ slabs


@pytest.mark.parametrize("rate", ["0", "5", "12", "18", "28", "3", "0.25"])
def test_before_the_reform_old_slabs_are_valid(rate):
    assert is_valid_slab(D(rate), date(2025, 9, 21))


@pytest.mark.parametrize("rate", ["12", "28"])
def test_12_and_28_are_not_valid_from_22_september_2025(rate):
    assert not is_valid_slab(D(rate), date(2025, 9, 22))
    assert not is_valid_slab(D(rate), date(2026, 8, 14))


def test_40_is_valid_only_from_the_reform():
    assert not is_valid_slab(D("40"), date(2025, 9, 21))
    assert is_valid_slab(D("40"), date(2025, 9, 22))


@pytest.mark.parametrize("rate", ["0", "5", "18", "3", "0.25"])
def test_main_and_special_slabs_stay_valid_after_the_reform(rate):
    assert is_valid_slab(D(rate), date(2026, 1, 1))


def test_decimal_spelling_does_not_matter():
    assert is_valid_slab(D("5.0"), date(2026, 1, 1))
    assert not is_valid_slab(D("7"), date(2026, 1, 1))


def test_dates_before_gst_use_the_first_table():
    assert slabs_on(date(2010, 1, 1)) == slabs_on(date(2017, 7, 1))
