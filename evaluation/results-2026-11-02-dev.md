# Evaluation results 2026-11-02 (dev split)

Model `gemini-3.5-flash-lite`, prompts `extract_v4`, `ledger_v1`, `review_v1`, confidence threshold 0.7. Corpus: 18 synthetic documents in this split; one document is 5.6 % of a figure, so read the numbers as a rough guide.

| Setup | Field acc. | Exact-doc | Status acc. | Sec/doc | API calls/doc |
|---|---|---|---|---|---|
| Gemini, reading A only | 99.0 % (207/209) | 94.4 % (17/18) | 100.0 % (18/18) | 6.0 | 2.00 |
| Gemini, A + B on doubt | 99.0 % (207/209) | 94.4 % (17/18) | 100.0 % (18/18) | 6.0 | 2.00 |
| Gemini, A + B always | 99.5 % (208/209) | 94.4 % (17/18) | 100.0 % (18/18) | 34.5 | 3.00 |

### Gemini, reading A only (`SECOND_READING=never`)

Documents evaluated: **18**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 99.0 % (207/209) |
| Line-item accuracy | 97.9 % (140/143) |
| Exact-document match (required fields) | 94.4 % (17/18) |
| Status accuracy | 100.0 % (18/18) |
| Error-code recall (expected codes found) | 83.3 % (5/6) |
| Error-code precision (found codes expected) | 83.3 % (5/6) |
| Ledger accuracy | 94.4 % (17/18) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (71/71) |
| Seconds per document (model time of its calls) | 6.0 |
| API calls per document | 2.00 |
| Tokens per document | 7,703 |
| Second reading ran on | 0/18 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 92.9 % (13/14) |
| buyer_name | 100.0 % (14/14) |
| cgst | 100.0 % (15/15) |
| igst | 100.0 % (15/15) |
| invoice_date | 100.0 % (18/18) |
| invoice_number | 100.0 % (18/18) |
| place_of_supply | 100.0 % (14/14) |
| round_off | 100.0 % (18/18) |
| sgst | 100.0 % (15/15) |
| taxable_value | 100.0 % (14/14) |
| total | 100.0 % (18/18) |
| vendor_gstin | 94.4 % (17/18) |
| vendor_name | 100.0 % (18/18) |

Documents that differ from the manifest:

- `15-grains-inter.pdf` (dev): status ready (want ready); ledger differs
- `19-blurred-scan.png` (dev): status ready (want ready); line 1: description got 'Printer toner carridge' want 'Printer toner cartridge', rate got Decimal('2.65') want '2650.00'; line 2: description got 'Spial binding sheets' want 'Spiral binding sheets'
- `23-missing-vendor-gstin.pdf` (dev): status needs_review (want needs_review); errors ['vendor_is_client'] (want ['missing_vendor_gstin']); vendor_gstin: got '23QXGPS4821K1ZU', want None; buyer_gstin: got None, want '23QXGPS4821K1ZU'
- `30-gst-inclusive-receipt.jpg` (dev): status ready (want ready); line 1: rate got None want '640.00'

Worst fields (wrong values, one example each):

- **vendor_gstin** 1 wrong of 18. `23-missing-vendor-gstin.pdf`: vendor_gstin: got '23QXGPS4821K1ZU', want None
- **buyer_gstin** 1 wrong of 14. `23-missing-vendor-gstin.pdf`: buyer_gstin: got None, want '23QXGPS4821K1ZU'

### Gemini, A + B on doubt (`SECOND_READING=on_doubt`)

Documents evaluated: **18**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 99.0 % (207/209) |
| Line-item accuracy | 97.9 % (140/143) |
| Exact-document match (required fields) | 94.4 % (17/18) |
| Status accuracy | 100.0 % (18/18) |
| Error-code recall (expected codes found) | 83.3 % (5/6) |
| Error-code precision (found codes expected) | 83.3 % (5/6) |
| Ledger accuracy | 94.4 % (17/18) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (71/71) |
| Seconds per document (model time of its calls) | 6.0 |
| API calls per document | 2.00 |
| Tokens per document | 7,703 |
| Second reading ran on | 0/18 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 92.9 % (13/14) |
| buyer_name | 100.0 % (14/14) |
| cgst | 100.0 % (15/15) |
| igst | 100.0 % (15/15) |
| invoice_date | 100.0 % (18/18) |
| invoice_number | 100.0 % (18/18) |
| place_of_supply | 100.0 % (14/14) |
| round_off | 100.0 % (18/18) |
| sgst | 100.0 % (15/15) |
| taxable_value | 100.0 % (14/14) |
| total | 100.0 % (18/18) |
| vendor_gstin | 94.4 % (17/18) |
| vendor_name | 100.0 % (18/18) |

Documents that differ from the manifest:

- `15-grains-inter.pdf` (dev): status ready (want ready); ledger differs
- `19-blurred-scan.png` (dev): status ready (want ready); line 1: description got 'Printer toner carridge' want 'Printer toner cartridge', rate got Decimal('2.65') want '2650.00'; line 2: description got 'Spial binding sheets' want 'Spiral binding sheets'
- `23-missing-vendor-gstin.pdf` (dev): status needs_review (want needs_review); errors ['vendor_is_client'] (want ['missing_vendor_gstin']); vendor_gstin: got '23QXGPS4821K1ZU', want None; buyer_gstin: got None, want '23QXGPS4821K1ZU'
- `30-gst-inclusive-receipt.jpg` (dev): status ready (want ready); line 1: rate got None want '640.00'

Worst fields (wrong values, one example each):

- **vendor_gstin** 1 wrong of 18. `23-missing-vendor-gstin.pdf`: vendor_gstin: got '23QXGPS4821K1ZU', want None
- **buyer_gstin** 1 wrong of 14. `23-missing-vendor-gstin.pdf`: buyer_gstin: got None, want '23QXGPS4821K1ZU'

### Gemini, A + B always (`SECOND_READING=always`)

Documents evaluated: **18**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 99.5 % (208/209) |
| Line-item accuracy | 97.9 % (140/143) |
| Exact-document match (required fields) | 94.4 % (17/18) |
| Status accuracy | 100.0 % (18/18) |
| Error-code recall (expected codes found) | 83.3 % (5/6) |
| Error-code precision (found codes expected) | 83.3 % (5/6) |
| Ledger accuracy | 94.4 % (17/18) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (71/71) |
| Seconds per document (model time of its calls) | 34.5 |
| API calls per document | 3.00 |
| Tokens per document | 10,830 |
| Second reading ran on | 18/18 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 100.0 % (14/14) |
| buyer_name | 100.0 % (14/14) |
| cgst | 100.0 % (15/15) |
| igst | 100.0 % (15/15) |
| invoice_date | 100.0 % (18/18) |
| invoice_number | 100.0 % (18/18) |
| place_of_supply | 100.0 % (14/14) |
| round_off | 100.0 % (18/18) |
| sgst | 100.0 % (15/15) |
| taxable_value | 100.0 % (14/14) |
| total | 100.0 % (18/18) |
| vendor_gstin | 94.4 % (17/18) |
| vendor_name | 100.0 % (18/18) |

Documents that differ from the manifest:

- `15-grains-inter.pdf` (dev): status ready (want ready); ledger differs
- `19-blurred-scan.png` (dev): status ready (want ready); line 1: description got 'Printer toner carridge' want 'Printer toner cartridge', rate got Decimal('2.65') want '2650.00'; line 2: description got 'Spial binding sheets' want 'Spiral binding sheets'
- `23-missing-vendor-gstin.pdf` (dev): status needs_review (want needs_review); errors ['vendor_is_client'] (want ['missing_vendor_gstin']); vendor_gstin: got '23QXGPS4821K1ZU', want None
- `30-gst-inclusive-receipt.jpg` (dev): status ready (want ready); line 1: rate got None want '640.00'

Worst fields (wrong values, one example each):

- **vendor_gstin** 1 wrong of 18. `23-missing-vendor-gstin.pdf`: vendor_gstin: got '23QXGPS4821K1ZU', want None

Live calls made in this run: 0. Run time 66 s.
