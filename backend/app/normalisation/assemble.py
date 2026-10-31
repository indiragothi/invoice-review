"""Turn the raw `Extraction` (strings as printed) into a typed `Invoice` or `Receipt`.

A value that cannot be normalised becomes None here. The original text stays available in the
`GroundedField.raw` of the same field, so rules can tell "not printed" from "unreadable".
"""

from app.normalisation.amounts import parse_amount, parse_percent
from app.normalisation.dates import parse_date
from app.normalisation.states import state_code_from_text
from app.normalisation.text import clean_text, normalise_gstin
from app.schemas.documents import Invoice, LineItem, Receipt, TaxLine
from app.schemas.extraction import ExtractedLineItem, ExtractedTaxLine, Extraction


def _line_item(item: ExtractedLineItem) -> LineItem:
    return LineItem(
        description=clean_text(item.description.value),
        hsn_sac=clean_text(item.hsn_sac.value),
        quantity=parse_amount(item.quantity.value),
        rate=parse_amount(item.rate.value),
        gst_rate=parse_percent(item.gst_rate.value),
        taxable_amount=parse_amount(item.taxable_amount.value),
    )


def _tax_line(line: ExtractedTaxLine) -> TaxLine:
    return TaxLine(
        head=line.head, rate=parse_percent(line.rate.value), amount=parse_amount(line.amount.value)
    )


def normalise_extraction(extraction: Extraction) -> Invoice | Receipt | None:
    """None when the document is neither an invoice nor a receipt."""
    e = extraction
    line_items = [_line_item(item) for item in e.line_items]
    tax_lines = [_tax_line(line) for line in e.tax_lines]

    if e.document_type == "invoice":
        return Invoice(
            vendor_name=clean_text(e.vendor_name.value),
            vendor_gstin=normalise_gstin(e.vendor_gstin.value),
            buyer_name=clean_text(e.buyer_name.value),
            buyer_gstin=normalise_gstin(e.buyer_gstin.value),
            invoice_number=clean_text(e.invoice_number.value),
            invoice_date=parse_date(e.invoice_date.value),
            place_of_supply_code=state_code_from_text(e.place_of_supply.value),
            line_items=line_items,
            taxable_value=parse_amount(e.taxable_value.value),
            tax_lines=tax_lines,
            round_off=parse_amount(e.round_off.value),
            total=parse_amount(e.total.value),
            amount_in_words=clean_text(e.amount_in_words.value),
        )
    if e.document_type == "receipt":
        return Receipt(
            merchant_name=clean_text(e.vendor_name.value),
            vendor_gstin=normalise_gstin(e.vendor_gstin.value),
            receipt_number=clean_text(e.invoice_number.value),
            receipt_date=parse_date(e.invoice_date.value),
            line_items=line_items,
            tax_lines=tax_lines,
            round_off=parse_amount(e.round_off.value),
            total=parse_amount(e.total.value),
        )
    return None
