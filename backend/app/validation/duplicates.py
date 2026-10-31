"""Duplicate keys and the duplicate rules. Pure: existing records come in as an argument.

Invoice key: vendor GSTIN + invoice number + financial year. Receipt key: merchant + date +
total (docs/policy-rules.md). The service (M3) passes the keys of this client's other
documents, `{document_id: key}`; it should leave out the document itself and records that are
rejected or failed, so a corrected re-issue of a rejected bill is not blocked.

A key is None until every part is known and settled: a missing GSTIN or number, a missing,
unreadable or ambiguous date, or a missing total. A half-known key would match too much.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.documents import Invoice, Receipt
from app.schemas.issues import IssueCode, ValidationIssue, make_issue
from app.validation.dates import financial_year


def _squash(text: str) -> str:
    """Case and punctuation do not make a different number: INV/26-27/001 == inv-26-27-001."""
    return re.sub(r"[^0-9a-z]", "", text.casefold())


@dataclass(frozen=True)
class InvoiceKey:
    vendor_gstin: str
    invoice_number: str  # squashed
    financial_year: str

    @property
    def text(self) -> str:
        return f"invoice|{self.vendor_gstin}|{self.invoice_number}|{self.financial_year}"


@dataclass(frozen=True)
class ReceiptKey:
    merchant: str  # squashed
    on: date
    total: Decimal

    @property
    def text(self) -> str:
        return f"receipt|{self.merchant}|{self.on.isoformat()}|{self.total.normalize():f}"


def invoice_key(invoice: Invoice) -> InvoiceKey | None:
    when = invoice.invoice_date
    if not invoice.vendor_gstin or not invoice.invoice_number:
        return None
    if when.value is None or when.ambiguous:
        return None
    number = _squash(invoice.invoice_number)
    if not number:
        return None
    return InvoiceKey(invoice.vendor_gstin, number, financial_year(when.value))


def receipt_key(receipt: Receipt) -> ReceiptKey | None:
    when = receipt.receipt_date
    if not receipt.merchant_name or when.value is None or when.ambiguous or receipt.total is None:
        return None
    merchant = _squash(receipt.merchant_name)
    if not merchant:
        return None
    return ReceiptKey(merchant, when.value, receipt.total)


def _first_match(key: object, existing: Mapping[str, object]) -> str | None:
    return next((doc_id for doc_id in sorted(existing) if existing[doc_id] == key), None)


def invoice_duplicate_issue(
    invoice: Invoice, existing: Mapping[str, InvoiceKey]
) -> ValidationIssue | None:
    key = invoice_key(invoice)
    if key is None or (match := _first_match(key, existing)) is None:
        return None
    return make_issue(
        IssueCode.DUPLICATE_INVOICE,
        f"Invoice {invoice.invoice_number} from {key.vendor_gstin} in FY {key.financial_year} "
        f"already exists for this client (document {match}).",
        "invoice_number",
    )


def receipt_duplicate_issue(
    receipt: Receipt, existing: Mapping[str, ReceiptKey]
) -> ValidationIssue | None:
    key = receipt_key(receipt)
    if key is None or (match := _first_match(key, existing)) is None:
        return None
    return make_issue(
        IssueCode.DUPLICATE_RECEIPT,
        f"A receipt from {receipt.merchant_name} on {key.on} for {key.total} already exists "
        f"for this client (document {match}).",
    )
