"""One export row per approved document (docs/policy-rules.md, invariant 4).

Pure: the service passes the normalised document and the facts around it. Money is `Decimal`,
dates are `date`; text coming from the bill is made safe for spreadsheets (`safe_text`).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.accounting.catalog import LEDGERS_BY_CODE
from app.clients import Client
from app.schemas.documents import Invoice, Receipt, TaxHead
from app.schemas.issues import Severity, ValidationIssue

Cell = str | Decimal | date | None

# (key, heading, kind) in the order of the file. kind: text | money | date
COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("document_id", "Document ID", "text"),
    ("client_id", "Client ID", "text"),
    ("client_name", "Client", "text"),
    ("client_gstin", "Client GSTIN", "text"),
    ("document_type", "Type", "text"),
    ("vendor_name", "Vendor / merchant", "text"),
    ("vendor_gstin", "Vendor GSTIN", "text"),
    ("number", "Invoice / receipt number", "text"),
    ("date", "Date", "date"),
    ("place_of_supply", "Place of supply (state code)", "text"),
    ("taxable_value", "Taxable value", "money"),
    ("cgst", "CGST", "money"),
    ("sgst", "SGST", "money"),
    ("utgst", "UTGST", "money"),
    ("igst", "IGST", "money"),
    ("cess", "Cess", "money"),
    ("round_off", "Round off", "money"),
    ("total", "Total", "money"),
    ("ledger_code", "Ledger code", "text"),
    ("ledger_name", "Ledger", "text"),
    ("ledger_overridden", "Ledger changed by reviewer", "text"),
    ("warnings", "Open warnings", "text"),
    ("approved_at", "Approved at", "text"),
    ("original_filename", "File name", "text"),
)

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str) -> str:
    """A spreadsheet would run `=HYPERLINK(...)`: a leading apostrophe makes it plain text."""
    return "'" + value if value.startswith(_FORMULA_STARTS) else value


@dataclass(frozen=True)
class ExportFacts:
    """What the row needs besides the normalised document."""

    document_id: str
    client: Client
    original_filename: str
    ledger: dict | None
    issues: list[ValidationIssue]
    approved_at: str | None


def _tax(document: Invoice | Receipt, head: TaxHead) -> Decimal | None:
    amounts = [t.amount for t in document.tax_lines if t.head == head and t.amount is not None]
    return sum(amounts, Decimal(0)) if amounts else None


def build_row(document: Invoice | Receipt, facts: ExportFacts) -> dict[str, Cell]:
    ledger = facts.ledger or {}
    code = ledger.get("selected_code")
    catalog_entry = LEDGERS_BY_CODE.get(code or "")
    if isinstance(document, Invoice):
        header: dict[str, Cell] = {
            "vendor_name": document.vendor_name,
            "number": document.invoice_number,
            "date": document.invoice_date.value,
            "place_of_supply": document.place_of_supply_code,
            "taxable_value": document.taxable_value,
        }
    else:
        header = {
            "vendor_name": document.merchant_name,
            "number": document.receipt_number,
            "date": document.receipt_date.value,
            "place_of_supply": None,
            "taxable_value": None,
        }
    row: dict[str, Cell] = {
        "document_id": facts.document_id,
        "client_id": facts.client.id,
        "client_name": facts.client.name,
        "client_gstin": facts.client.gstin,
        "document_type": document.document_type,
        "vendor_gstin": document.vendor_gstin,
        **header,
        "cgst": _tax(document, "CGST"),
        "sgst": _tax(document, "SGST"),
        "utgst": _tax(document, "UTGST"),
        "igst": _tax(document, "IGST"),
        "cess": _tax(document, "CESS"),
        "round_off": document.round_off,
        "total": document.total,
        "ledger_code": code,
        "ledger_name": catalog_entry.name if catalog_entry else None,
        "ledger_overridden": "yes" if ledger.get("overridden") else "no",
        "warnings": ", ".join(
            sorted({i.code.value for i in facts.issues if i.severity == Severity.WARNING})
        )
        or None,
        "approved_at": facts.approved_at,
        "original_filename": facts.original_filename,
    }
    return {
        key: safe_text(value) if isinstance(value, str) else value for key, value in row.items()
    }
