"""Receipt rules (docs/policy-rules.md). Pure: everything comes in as arguments.

Receipts need fewer fields than invoices: no invoice number, no buyer GSTIN, GST may be absent.
Not here by design: the two-reading and same-file warnings (pipeline).
"""

from collections.abc import Mapping
from datetime import date

from app.config import APP_CONFIG
from app.schemas.documents import Receipt
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, ValidationIssue, make_issue
from app.validation import tax
from app.validation.duplicates import ReceiptKey, receipt_duplicate_issue
from app.validation.shared import (
    date_issues,
    gstin_issue,
    low_confidence_issues,
    ungrounded_issues,
)

# Field keys as grounding names them (the merchant is extracted as `vendor_name`).
REQUIRED_FIELDS = ("vendor_name", "invoice_date", "total")


def validate_receipt(
    receipt: Receipt,
    fields: dict[str, GroundedField],
    today: date,
    threshold: float = APP_CONFIG.confidence_threshold,
    existing: Mapping[str, ReceiptKey] | None = None,
) -> list[ValidationIssue]:
    """All receipt rules. `existing` = keys of this client's other documents (see duplicates)."""
    issues: list[ValidationIssue] = []

    if not receipt.merchant_name:
        issues.append(
            make_issue(IssueCode.MISSING_MERCHANT, "The merchant name is missing.", "vendor_name")
        )

    # Policy lists no "old" warning for receipts.
    issues += date_issues(
        receipt.receipt_date, today, "invoice_date", IssueCode.MISSING_RECEIPT_DATE, warn_old=False
    )

    if receipt.total is None:
        issues.append(make_issue(IssueCode.MISSING_TOTAL, "The total is missing.", "total"))

    # A GSTIN is optional on a receipt, but if one is printed it must be valid.
    if receipt.vendor_gstin and (
        problem := gstin_issue(receipt.vendor_gstin, "vendor_gstin", IssueCode.INVALID_VENDOR_GSTIN)
    ):
        issues.append(problem)

    totals = tax.tax_totals(receipt.tax_lines)
    computed = tax.receipt_computed_total(receipt.line_items, totals, receipt.round_off)
    if (
        computed is not None
        and receipt.total is not None
        and not totals.unreadable
        and tax.differs(computed, receipt.total)
    ):
        issues.append(
            make_issue(
                IssueCode.LINE_ITEMS_SUM_MISMATCH,
                f"Line items + tax + round-off is {computed}, but the total is {receipt.total}.",
                "line_items",
            )
        )

    if not receipt.tax_lines:
        issues.append(
            make_issue(
                IssueCode.MISSING_TAX_BREAKUP,
                "No tax breakup is printed. Only the total can be recorded.",
                "tax_lines",
            )
        )

    required = REQUIRED_FIELDS + (("vendor_gstin",) if receipt.vendor_gstin else ())
    if duplicate := receipt_duplicate_issue(receipt, existing or {}):
        issues.append(duplicate)

    issues += ungrounded_issues(fields, required)
    issues += low_confidence_issues(fields, required, threshold)
    return issues
