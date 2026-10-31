# Samples

Ground-truth documents for evaluation. Everything here is **fictional**: businesses, addresses and GSTINs are invented (GSTINs pass the checksum but use made-up PANs). Never commit real client bills.

Do not edit these files by hand. Regenerate them from `backend/`:

```powershell
uv run --locked --no-sync python -m scripts.generate_samples
```

The script writes `generated/` and `manifest.json` in the same run, checks that each document contains exactly the problem it is meant to test, and produces byte-identical output on every run.

## Current set (12)

| # | File | Type | Tests | Expected |
|---|---|---|---|---|
| 01 | `intra-classic.pdf` | invoice | CGST + SGST, classic layout | ready |
| 02 | `intra-compact.pdf` | invoice | CGST + SGST, compact layout, lakh amounts | ready |
| 03 | `inter-classic.pdf` | invoice | IGST, fixed-asset purchase | ready |
| 04 | `inter-compact.pdf` | invoice | IGST, services (SAC), client C003 | ready |
| 05 | `invalid-vendor-gstin.pdf` | invoice | Vendor GSTIN checksum fails | needs_review |
| 06 | `total-mismatch.pdf` | invoice | Printed total ₹1,000 too high | needs_review |
| 07 | `wrong-tax-split.pdf` | invoice | IGST charged on an intra-state supply | needs_review |
| 08 | `buyer-not-client.pdf` | invoice | Billed to a different company | needs_review |
| 09 | `two-page.pdf` | invoice | 34 line items over two pages, 5 % and 18 % mixed | ready |
| 10 | `scan-quality.png` | invoice | Tilted, blurred scan; no text layer (OCR path) | ready |
| 11 | `fuel-receipt.jpg` | receipt | Phone photo, fuel outside GST | ready |
| 12 | `restaurant-receipt.jpg` | receipt | Phone photo, 5 % GST | ready |

Splits: dev = 01, 03, 05, 07, 08, 09, 11 · test = 02, 04, 06, 10, 12. The corpus grows to 36+ in milestone M5 (see `docs/evaluation.md`).

## manifest.json

One entry per document: `file`, `split`, `client`, `type`, `scenario`, `pages`, `text_layer`, `expected_status`, `expected_errors` (snake_case codes from `docs/policy-rules.md`), `expected_ledger`, and `fields` (normalised values: ISO dates, amounts as strings with two decimals, line items).
