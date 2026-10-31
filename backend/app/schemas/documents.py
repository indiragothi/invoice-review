"""Normalised documents: typed values that the pure rules in `validation/` work on.

Money is `Decimal`, dates are `date`. A value that could not be normalised is `None` and the
rules report it. Provenance (box, source, confidence) lives beside these in `GroundedField`s,
keyed by field name, so rules never need it except for the grounding / confidence checks.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TaxHead = Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]


class LineItem(BaseModel):
    description: str | None = None
    hsn_sac: str | None = None
    quantity: Decimal | None = None
    rate: Decimal | None = None
    gst_rate: Decimal | None = Field(default=None, description="Percent, e.g. 18.")
    taxable_amount: Decimal | None = None


class TaxLine(BaseModel):
    head: TaxHead
    rate: Decimal | None = Field(default=None, description="Percent, e.g. 9.")
    amount: Decimal | None = None


class NormalisedDate(BaseModel):
    """A parsed date. `ambiguous` means day and month could be swapped and nothing settled it."""

    value: date | None = None
    ambiguous: bool = False


class Invoice(BaseModel):
    document_type: Literal["invoice"] = "invoice"
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: NormalisedDate = Field(default_factory=NormalisedDate)
    place_of_supply_code: str | None = Field(default=None, description="2-digit GST state code.")
    reverse_charge: bool = False
    line_items: list[LineItem] = Field(default_factory=list)
    taxable_value: Decimal | None = None
    tax_lines: list[TaxLine] = Field(default_factory=list)
    round_off: Decimal | None = None
    total: Decimal | None = None
    amount_in_words: str | None = None


class Receipt(BaseModel):
    document_type: Literal["receipt"] = "receipt"
    merchant_name: str | None = None
    vendor_gstin: str | None = Field(default=None, description="Only if printed on the receipt.")
    receipt_number: str | None = None
    receipt_date: NormalisedDate = Field(default_factory=NormalisedDate)
    line_items: list[LineItem] = Field(default_factory=list)
    tax_lines: list[TaxLine] = Field(default_factory=list)
    round_off: Decimal | None = None
    total: Decimal | None = None
