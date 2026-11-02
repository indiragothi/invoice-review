# Samples

Ground-truth documents for evaluation. Everything here is **fictional**: businesses, addresses and GSTINs are invented (GSTINs pass the checksum but use made-up PANs). Never commit real client bills.

Do not edit these files by hand. Regenerate them from `backend/`:

```powershell
uv run --locked --no-sync python -m scripts.generate_samples
```

The script writes `generated/` and `manifest.json` in the same run, checks that each document contains exactly the problem it is meant to test, and produces byte-identical output on every run.

## Current set (30)

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
| 13 | `furniture-intra.pdf` | invoice | CGST + SGST, fixed assets | ready |
| 14 | `packaging-intra.pdf` | invoice | Compact layout, client C002 (Pune) | ready |
| 15 | `grains-inter.pdf` | invoice | IGST, client C002, 5 % | ready |
| 16 | `dental-inter.pdf` | invoice | IGST, compact, client C003 | ready |
| 17 | `three-page.pdf` | invoice | 76 line items over three pages | ready |
| 18 | `beverages-mixed-rates.pdf` | invoice | 40 %, 18 % and 5 % on one bill | ready |
| 19 | `blurred-scan.png` | invoice | Heavy blur, no text layer | ready |
| 20 | `skewed-scan.png` | invoice | Tilted about 4-5 degrees, no text layer | ready |
| 21 | `low-resolution-scan.png` | invoice | 85 dpi scan, no text layer | ready |
| 22 | `phone-photo-invoice.jpg` | invoice | Invoice photographed on a dark surface | ready |
| 23 | `missing-vendor-gstin.pdf` | invoice | No vendor GSTIN printed | needs_review |
| 24 | `duplicate-invoice.pdf` | invoice | Same vendor and number as 01, other layout | ready alone; needs_review after 01 |
| 25 | `ambiguous-date.pdf` | invoice | Date 04/05/2026 (4 May or 5 April) | needs_review |
| 26 | `invalid-buyer-gstin.pdf` | invoice | Buyer GSTIN fails the checksum | needs_review |
| 27 | `stationery-receipt.jpg` | receipt | Phone photo, 18 % GST itemised | ready |
| 28 | `cafe-receipt.jpg` | receipt | Phone photo, 5 % GST, client C002 | ready |
| 29 | `petrol-receipt.jpg` | receipt | Phone photo, petrol outside GST, client C002 | ready |
| 30 | `gst-inclusive-receipt.jpg` | receipt | Prices already include GST (probe for a false sum mismatch) | ready |

Splits: dev (18) = 01, 03, 05, 07, 08, 09, 11, 13, 15, 17, 19, 20, 23, 25, 26, 27, 29, 30 · test (12) = 02, 04, 06, 10, 12, 14, 16, 18, 21, 22, 24, 28. The corpus is 30 documents for the M5 evaluation (decision D15; the first plan was 36+). 01-12 are unchanged, byte for byte, so their cached model readings stay valid.

The offline `playground/*_samples.py` scripts that read `output/extract/` (the old `extract_v1` cache) stop at document 13. Cached answers of the production prompt `extract_v2` exist for the 18 dev documents only.

`24-duplicate-invoice.pdf` is a normal invoice on its own. Uploaded after 01 for the same client it must raise `duplicate_invoice`; the manifest records that in `duplicate_of` and `expected_when_original_exists`.

## manifest.json

One entry per document: `file`, `split`, `client`, `type`, `scenario`, `pages`, `text_layer`, `expected_status`, `expected_errors` (snake_case codes from `docs/policy-rules.md`), `expected_ledger`, and `fields` (normalised values: ISO dates, amounts as strings with two decimals, line items).
