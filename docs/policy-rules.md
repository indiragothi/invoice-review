# Policy Rules

These rules are plain, testable Python in one pure module (`backend/app/validation/`). Models provide evidence; **these rules decide**. A **blocking error** must be fixed before a record can be approved. A **warning** is shown but does not block approval.

- Money is compared as `Decimal`, never `float`. Rounding tolerance is **₹1.00** unless stated.
- Dates on Indian bills are read as **DD-MM-YYYY** first. An ambiguous date (e.g. 04/05/2025) is never silently guessed: it gets `AMBIGUOUS_DATE` unless the layout or other dates settle it.
- Financial year runs **1 April – 31 March**.
- Every document is uploaded **for a client** (the firm's customer), who has a name, GSTIN and state code.

## Document types

| Type | Meaning |
|---|---|
| `invoice` | GST tax invoice from a registered supplier (has GSTIN, tax breakup) |
| `receipt` | Retail / fuel / restaurant / expense receipt. Usually no buyer details; GST may be absent or only a total |

## Invoice rules

### Blocking errors

| Code | Rule |
|---|---|
| `MISSING_VENDOR_NAME` | Vendor name is empty |
| `MISSING_INVOICE_NUMBER` | Invoice number is empty |
| `MISSING_INVOICE_DATE` | Date is missing |
| `INVALID_DATE` | Date cannot be parsed, or is in the future |
| `AMBIGUOUS_DATE` | Day and month could be swapped and nothing settles it |
| `MISSING_TOTAL` | Grand total is missing |
| `MISSING_VENDOR_GSTIN` | Vendor GSTIN is missing on a tax invoice |
| `INVALID_VENDOR_GSTIN` | Vendor GSTIN fails the 15-character format or checksum |
| `INVALID_BUYER_GSTIN` | Buyer GSTIN is present but fails format / checksum |
| `BUYER_NOT_CLIENT` | Buyer GSTIN is present and differs from the selected client's GSTIN (ITC would be at risk) |
| `LINE_ITEMS_SUM_MISMATCH` | Sum of line taxable amounts differs from taxable value by more than tolerance |
| `TOTAL_MISMATCH` | taxable value + CGST + SGST + IGST + cess + round-off differs from grand total by more than tolerance |
| `TAX_SPLIT_INCONSISTENT` | Intra-state supply must have CGST = SGST and no IGST; inter-state supply must have IGST only |
| `UNGROUNDED_REQUIRED_FIELD` | A required value could not be found in the words the model cited |
| `DUPLICATE_INVOICE` | Same vendor GSTIN + invoice number + financial year already exists for this client |

**Intra vs inter-state:** compare the vendor's state (first 2 digits of vendor GSTIN) with the place of supply. If place of supply is not printed, use the buyer GSTIN state, then the client's state code.

### Warnings

| Code | Rule |
|---|---|
| `MISSING_BUYER_GSTIN` | Buyer GSTIN is absent (B2C bill, ITC may not be claimable) |
| `MISSING_HSN_SAC` | A line item has no HSN / SAC code |
| `UNUSUAL_TAX_RATE` | A line's effective GST rate is not a valid slab **for the invoice date** (see below) |
| `INVOICE_NUMBER_TOO_LONG` | Invoice number is longer than 16 characters (CGST Rule 46) |
| `AMOUNT_IN_WORDS_MISMATCH` | The total written in words (lakh / crore aware) differs from the figure |
| `OLD_INVOICE` | Invoice date is more than 12 months old |
| `REVERSE_CHARGE` | Invoice says tax is payable on reverse charge; needs the accountant's attention |
| `LOW_CONFIDENCE_FIELD` | A required field's confidence is below the threshold |
| `READINGS_DISAGREE` | The two readings disagree on a field |
| `DUPLICATE_FILE` | The exact same file was uploaded before |

## Receipt rules

Receipts need fewer fields. Requiring an invoice number or buyer GSTIN on a petrol-pump slip would be wrong.

### Blocking errors

| Code | Rule |
|---|---|
| `MISSING_MERCHANT` | Merchant name is empty |
| `MISSING_RECEIPT_DATE` / `INVALID_DATE` / `AMBIGUOUS_DATE` | As for invoices |
| `MISSING_TOTAL` | Total is missing |
| `LINE_ITEMS_SUM_MISMATCH` | If line items exist, their sum plus tax must match the total |
| `INVALID_VENDOR_GSTIN` | Only if a GSTIN is printed and it fails format / checksum |
| `UNGROUNDED_REQUIRED_FIELD` | As for invoices |
| `DUPLICATE_RECEIPT` | Same merchant + date + total already exists for this client |

### Warnings

`LOW_CONFIDENCE_FIELD`, `READINGS_DISAGREE`, `MISSING_TAX_BREAKUP`, `DUPLICATE_FILE`.

## GSTIN validation

A GSTIN is 15 characters: 2-digit state code, 10-character PAN, 1 entity number, the letter `Z` (default), and 1 check character. We validate format, state code and checksum **offline** (`python-stdnum`, `in.gstin`). We do **not** claim the GSTIN is active: that needs the GST portal, which is out of scope.

OCR often confuses `0/O`, `1/I`, `5/S`, `8/B`. The validator may **suggest** a one-character fix that makes the checksum pass, but never applies it silently. The human accepts it.

## GST rate slabs are date-dependent

Rate slabs changed with the GST rate rationalisation effective **22 September 2025** (main slabs moved towards 0 / 5 / 18 %, with a 40 % slab for some goods; special rates such as 0.25 % and 3 % remain). Before that, the main slabs were 0 / 5 / 12 / 18 / 28 %.

Slabs live in a dated config table (`validation/tax_slabs.py`), not in code branches. **Verify the table against official CBIC notifications before relying on it.** A mismatch only raises a warning, because transition-period bills and special items are common.

## Review status

| Status | Condition |
|---|---|
| `processing` | Pipeline running |
| `ready` | No blocking errors and every required field grounded and above the confidence threshold. Can be approved one by one or in bulk |
| `needs_review` | Any blocking error, or a required field below threshold. Must be opened and fixed |
| `failed` | Nothing usable was extracted (unreadable file, provider error after retries). Can be retried |
| `approved` / `rejected` | Final human decision. The record is locked |

### Invariants

1. A record with an open blocking error can never become `approved`. Enforced in the service layer (`409 Conflict`), not only in the UI.
2. Editing a field sets its source to `human`, sets confidence to 1.0, clears its low-confidence / disagreement warnings, and re-runs every rule.
3. A decided record is immutable.
4. Nothing is exported unless it is `approved`.

## Confidence

Per-field confidence is computed by code:

| Signal | Effect |
|---|---|
| Text source | PDF text layer = 1.0; OCR = mean OCR confidence of the evidence words |
| Grounding | Ungrounded value → confidence 0 |
| Agreement | Readings agree → kept; differ → capped at 0.5 |
| Format check | Value fails its own format (GSTIN, date, amount) → capped at 0.3 |

A model's self-reported confidence is never used. The threshold (default 0.80) is tuned on the dev split of the evaluation set, never on the test split.
