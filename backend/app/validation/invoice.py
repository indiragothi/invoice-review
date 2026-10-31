"""Invoice rules (docs/policy-rules.md). Pure: everything comes in as arguments.

Models provide evidence, these rules decide. This module grows over two slices: the header
rules here (who, what number, when, GSTINs, grounding), then the money and line rules.
"""

from datetime import date

from app.clients import Client
from app.config import APP_CONFIG
from app.schemas.documents import Invoice
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, ValidationIssue, make_issue
from app.validation.shared import (
    date_issues,
    gstin_issue,
    low_confidence_issues,
    ungrounded_issues,
)

# Field keys as grounding names them.
REQUIRED_FIELDS = ("vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "total")

MAX_INVOICE_NUMBER_LENGTH = 16  # CGST Rule 46


def header_issues(
    invoice: Invoice,
    fields: dict[str, GroundedField],
    client: Client,
    today: date,
    threshold: float = APP_CONFIG.confidence_threshold,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not invoice.vendor_name:
        issues.append(
            make_issue(IssueCode.MISSING_VENDOR_NAME, "The vendor name is missing.", "vendor_name")
        )

    if not invoice.invoice_number:
        issues.append(
            make_issue(
                IssueCode.MISSING_INVOICE_NUMBER, "The invoice number is missing.", "invoice_number"
            )
        )
    elif len(invoice.invoice_number) > MAX_INVOICE_NUMBER_LENGTH:
        issues.append(
            make_issue(
                IssueCode.INVOICE_NUMBER_TOO_LONG,
                f"The invoice number has {len(invoice.invoice_number)} characters; "
                f"CGST Rule 46 allows at most {MAX_INVOICE_NUMBER_LENGTH}.",
                "invoice_number",
            )
        )

    issues += date_issues(
        invoice.invoice_date, today, "invoice_date", IssueCode.MISSING_INVOICE_DATE
    )

    if invoice.total is None:
        issues.append(make_issue(IssueCode.MISSING_TOTAL, "The grand total is missing.", "total"))

    issues += _gstin_issues(invoice, client)

    if invoice.reverse_charge:
        issues.append(
            make_issue(
                IssueCode.REVERSE_CHARGE,
                "Tax is payable on reverse charge. Needs the accountant's attention.",
            )
        )

    issues += ungrounded_issues(fields, REQUIRED_FIELDS)
    issues += low_confidence_issues(fields, REQUIRED_FIELDS, threshold)
    return issues


def _gstin_issues(invoice: Invoice, client: Client) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not invoice.vendor_gstin:
        issues.append(
            make_issue(
                IssueCode.MISSING_VENDOR_GSTIN,
                "The vendor GSTIN is missing on a tax invoice.",
                "vendor_gstin",
            )
        )
    elif problem := gstin_issue(
        invoice.vendor_gstin, "vendor_gstin", IssueCode.INVALID_VENDOR_GSTIN
    ):
        issues.append(problem)

    if not invoice.buyer_gstin:
        issues.append(
            make_issue(
                IssueCode.MISSING_BUYER_GSTIN,
                "No buyer GSTIN is printed (B2C bill); input tax credit may not be claimable.",
                "buyer_gstin",
            )
        )
    elif problem := gstin_issue(invoice.buyer_gstin, "buyer_gstin", IssueCode.INVALID_BUYER_GSTIN):
        issues.append(problem)
    elif invoice.buyer_gstin != client.gstin:
        issues.append(
            make_issue(
                IssueCode.BUYER_NOT_CLIENT,
                f"The bill is made out to {invoice.buyer_gstin}, not to {client.name} "
                f"({client.gstin}). Input tax credit would be at risk.",
                "buyer_gstin",
            )
        )
    return issues
