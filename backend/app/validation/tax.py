"""Tax arithmetic for invoices and receipts. Pure functions on normalised values.

These return facts (supply type, sums, differences, a split problem). Turning them into issues
with codes and messages is the job of the invoice / receipt rules.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.config import APP_CONFIG
from app.normalisation.states import state_code_from_gstin
from app.schemas.documents import LineItem, TaxLine

ZERO = Decimal(0)

SupplyType = Literal["intra", "inter"]
# igst_on_intra: IGST charged on a same-state supply.
# cgst_sgst_unequal: intra-state CGST and SGST (or UTGST) differ.
# state_tax_on_inter: CGST / SGST / UTGST charged on an other-state supply.
SplitProblem = Literal["igst_on_intra", "cgst_sgst_unequal", "state_tax_on_inter"]


def supply_type(
    vendor_gstin: str | None,
    place_of_supply_code: str | None,
    buyer_gstin: str | None,
    client_state_code: str | None,
) -> SupplyType | None:
    """Intra-state if the vendor's state equals the place of supply, else inter-state.

    If the place of supply is not printed, use the buyer GSTIN state, then the client's state
    code (docs/policy-rules.md). None when either side cannot be determined.
    """
    vendor_state = state_code_from_gstin(vendor_gstin)
    destination = place_of_supply_code or state_code_from_gstin(buyer_gstin) or client_state_code
    if vendor_state is None or destination is None:
        return None
    return "intra" if vendor_state == destination else "inter"


@dataclass(frozen=True)
class TaxTotals:
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    utgst: Decimal = ZERO
    igst: Decimal = ZERO
    cess: Decimal = ZERO
    unreadable: bool = False  # some tax row had an amount that could not be read

    @property
    def total(self) -> Decimal:
        return self.cgst + self.sgst + self.utgst + self.igst + self.cess

    @property
    def any_tax(self) -> bool:
        return self.total != ZERO


def tax_totals(tax_lines: list[TaxLine]) -> TaxTotals:
    """Add up every tax row per head (a document can list several rates per head)."""
    sums = {"CGST": ZERO, "SGST": ZERO, "UTGST": ZERO, "IGST": ZERO, "CESS": ZERO}
    unreadable = False
    for line in tax_lines:
        if line.amount is None:
            unreadable = True
        else:
            sums[line.head] += line.amount
    return TaxTotals(
        cgst=sums["CGST"],
        sgst=sums["SGST"],
        utgst=sums["UTGST"],
        igst=sums["IGST"],
        cess=sums["CESS"],
        unreadable=unreadable,
    )


def tax_split_problem(
    supply: SupplyType,
    totals: TaxTotals,
    tolerance: Decimal = APP_CONFIG.money_tolerance,
) -> SplitProblem | None:
    """Intra-state: CGST = SGST (or UTGST), no IGST. Inter-state: IGST only.

    A document with no tax at all (exempt, nil-rated) has no split problem.
    """
    state_side = totals.sgst + totals.utgst
    if supply == "intra":
        if totals.igst != ZERO:
            return "igst_on_intra"
        if abs(totals.cgst - state_side) > tolerance:
            return "cgst_sgst_unequal"
        return None
    if totals.cgst != ZERO or state_side != ZERO:
        return "state_tax_on_inter"
    return None


def line_items_sum(items: list[LineItem]) -> Decimal | None:
    """Sum of line taxable amounts; None if there are no lines or any amount is unreadable."""
    if not items or any(item.taxable_amount is None for item in items):
        return None
    return sum((item.taxable_amount for item in items), ZERO)


def invoice_computed_total(
    taxable_value: Decimal | None, totals: TaxTotals, round_off: Decimal | None
) -> Decimal | None:
    """Taxable value + CGST + SGST + UTGST + IGST + cess + round-off. None without a base."""
    if taxable_value is None:
        return None
    return taxable_value + totals.total + (round_off or ZERO)


def receipt_computed_total(
    items: list[LineItem], totals: TaxTotals, round_off: Decimal | None
) -> Decimal | None:
    """Line amounts + tax + round-off. None if there are no usable line items."""
    base = line_items_sum(items)
    if base is None:
        return None
    return base + totals.total + (round_off or ZERO)


def differs(a: Decimal, b: Decimal, tolerance: Decimal = APP_CONFIG.money_tolerance) -> bool:
    """True if the two amounts differ by more than the tolerance (exactly equal to it is fine)."""
    return abs(a - b) > tolerance
