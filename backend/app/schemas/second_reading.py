"""What the second, independent reading returns: plain values read from the page images.

No evidence word IDs here: the model looks at pictures, not at numbered words. Code later finds
each value it supplied in the page words (`pipeline/agreement.py`) before it is trusted.
The field names match `Extraction`, so the two readings can be compared field by field.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SecondLineItem(BaseModel):
    description: str | None = None
    hsn_sac: str | None = None
    quantity: str | None = None
    rate: str | None = None
    gst_rate: str | None = Field(default=None, description="GST rate in percent, if printed.")
    taxable_amount: str | None = Field(default=None, description="Line amount before GST.")


class SecondTaxLine(BaseModel):
    head: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    rate: str | None = Field(default=None, description="Rate in percent as printed, e.g. '9'.")
    amount: str | None = None


class SecondReading(BaseModel):
    vendor_name: str | None = Field(description="Seller / merchant name only, as printed.")
    vendor_gstin: str | None = Field(description="Seller's 15-character GSTIN as printed.")
    buyer_name: str | None = Field(description="Billed-to party. Null on receipts.")
    buyer_gstin: str | None = Field(description="Billed-to party's GSTIN, if printed.")
    invoice_number: str | None = Field(description="Invoice / bill / receipt number.")
    invoice_date: str | None = Field(description="Date as printed.")
    place_of_supply: str | None = Field(description="Place of supply as printed, if any.")
    line_items: list[SecondLineItem]
    taxable_value: str | None = Field(description="Total before tax (taxable value / sub total).")
    tax_lines: list[SecondTaxLine] = Field(
        description="Every tax row of the totals section, one per head and rate, in printed order."
    )
    round_off: str | None
    total: str | None = Field(description="Grand total payable.")
    amount_in_words: str | None = Field(description="Total written in words, if printed.")
