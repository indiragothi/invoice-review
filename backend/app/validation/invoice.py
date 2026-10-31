"""Invoice rules (docs/policy-rules.md). Pure: everything comes in as arguments.

Models provide evidence, these rules decide. `header_issues`: who, what number, when, GSTINs,
grounding. `amount_issues`: totals, tax split, line items. `validate_invoice` runs both.

Not here by design: duplicates (need existing records), and the two-reading and same-file
warnings (pipeline).
"""

from datetime import date

from app.clients import Client
from app.config import APP_CONFIG
from app.normalisation.words import parse_amount_in_words
from app.schemas.documents import Invoice
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, ValidationIssue, make_issue
from app.validation import tax
from app.validation.shared import (
    date_issues,
    gstin_issue,
    low_confidence_issues,
    ungrounded_issues,
)
from app.validation.tax_slabs import is_valid_slab

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


def amount_issues(invoice: Invoice, client: Client) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    totals = tax.tax_totals(invoice.tax_lines)

    supply = tax.supply_type(
        invoice.vendor_gstin, invoice.place_of_supply_code, invoice.buyer_gstin, client.state_code
    )
    # With an unreadable tax amount the sums are wrong, so neither the split nor the total is
    # judged (the unreadable value is reported where it is read).
    if supply and not totals.unreadable and (problem := tax.tax_split_problem(supply, totals)):
        issues.append(
            make_issue(IssueCode.TAX_SPLIT_INCONSISTENT, _SPLIT_MESSAGES[problem], "tax_lines")
        )

    lines = tax.line_items_sum(invoice.line_items)
    if lines is not None and invoice.taxable_value is not None:
        if tax.differs(lines, invoice.taxable_value):
            issues.append(
                make_issue(
                    IssueCode.LINE_ITEMS_SUM_MISMATCH,
                    f"The line items add up to {lines}, but the taxable value is "
                    f"{invoice.taxable_value}.",
                    "line_items",
                )
            )

    computed = tax.invoice_computed_total(invoice.taxable_value, totals, invoice.round_off)
    if computed is not None and invoice.total is not None and not totals.unreadable:
        if tax.differs(computed, invoice.total):
            issues.append(
                make_issue(
                    IssueCode.TOTAL_MISMATCH,
                    f"Taxable value + tax + round-off is {computed}, but the total is "
                    f"{invoice.total}.",
                    "total",
                )
            )

    issues += _line_item_issues(invoice)

    # Words that cannot be read as an amount are not judged: no guessing either way.
    in_words = parse_amount_in_words(invoice.amount_in_words)
    if in_words is not None and invoice.total is not None and tax.differs(in_words, invoice.total):
        issues.append(
            make_issue(
                IssueCode.AMOUNT_IN_WORDS_MISMATCH,
                f"The total in words is {in_words}, but the figure is {invoice.total}.",
                "amount_in_words",
            )
        )
    return issues


_SPLIT_MESSAGES = {
    "igst_on_intra": "IGST is charged on a supply within the same state.",
    "cgst_sgst_unequal": "CGST and SGST are not equal on a supply within the same state.",
    "state_tax_on_inter": "CGST / SGST is charged on a supply to another state.",
}


def _line_item_issues(invoice: Invoice) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    rate_date = invoice.invoice_date.value
    for index, item in enumerate(invoice.line_items):
        if not item.hsn_sac:
            issues.append(
                make_issue(
                    IssueCode.MISSING_HSN_SAC,
                    f"Line {index + 1} has no HSN / SAC code.",
                    f"line_items[{index}].hsn_sac",
                )
            )
        if (
            item.gst_rate is not None
            and rate_date is not None
            and not is_valid_slab(item.gst_rate, rate_date)
        ):
            issues.append(
                make_issue(
                    IssueCode.UNUSUAL_TAX_RATE,
                    f"Line {index + 1}: {item.gst_rate}% is not a GST slab on {rate_date}.",
                    f"line_items[{index}].gst_rate",
                )
            )
    return issues


def validate_invoice(
    invoice: Invoice,
    fields: dict[str, GroundedField],
    client: Client,
    today: date,
    threshold: float = APP_CONFIG.confidence_threshold,
) -> list[ValidationIssue]:
    return header_issues(invoice, fields, client, today, threshold) + amount_issues(invoice, client)
