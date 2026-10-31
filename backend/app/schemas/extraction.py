"""What the LLM returns for one document: raw printed values, each with evidence word IDs.

Values are copied exactly as printed (e.g. "1,23,456.00", "14-08-2026"). Turning them into
dates and Decimals is code's job (normalisation), not the model's. These models double as the
structured-output schema sent to the provider, so field descriptions are written for the model.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Evidenced(BaseModel):
    value: str | None = Field(
        description="The value exactly as printed on the document, or null if it is not printed."
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="IDs of the words that contain this value, e.g. ['w41', 'w42']. "
        "Empty only when value is null.",
    )


class ExtractedLineItem(BaseModel):
    description: Evidenced
    hsn_sac: Evidenced
    quantity: Evidenced
    rate: Evidenced
    gst_rate: Evidenced = Field(description="GST rate in percent for this line, if printed.")
    taxable_amount: Evidenced = Field(description="Line amount before GST.")


class ExtractedTaxLine(BaseModel):
    head: Literal["CGST", "SGST", "UTGST", "IGST", "CESS"]
    rate: Evidenced = Field(description="Rate in percent as printed, e.g. '9' from 'CGST @ 9%'.")
    amount: Evidenced


class Extraction(BaseModel):
    document_type: Literal["invoice", "receipt", "other"] = Field(
        description="invoice: a GST tax invoice or supplier bill with buyer details. "
        "receipt: a retail, fuel, restaurant or other paid receipt without buyer details. "
        "other: anything that is not a financial bill."
    )
    classification_reason: str = Field(description="One short sentence.")

    vendor_name: Evidenced = Field(description="Seller / merchant name.")
    vendor_gstin: Evidenced = Field(description="Seller's 15-character GSTIN.")
    buyer_name: Evidenced = Field(description="Billed-to party. Null on receipts.")
    buyer_gstin: Evidenced = Field(description="Billed-to party's GSTIN, if printed.")
    invoice_number: Evidenced = Field(description="Invoice / bill / receipt number.")
    invoice_date: Evidenced = Field(description="Invoice or receipt date as printed.")
    place_of_supply: Evidenced = Field(description="Place of supply as printed, if any.")

    line_items: list[ExtractedLineItem]

    taxable_value: Evidenced = Field(description="Total before tax (taxable value / sub total).")
    tax_lines: list[ExtractedTaxLine] = Field(
        description="Every tax row in the totals section, one per head and rate, in printed "
        "order. Empty if no tax is printed."
    )
    round_off: Evidenced
    total: Evidenced = Field(description="Grand total payable.")
    amount_in_words: Evidenced = Field(description="Total written in words, if printed.")
