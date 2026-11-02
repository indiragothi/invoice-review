# Evaluation results 2026-11-02 (test split)

Model `gemini-3.5-flash-lite`, prompts `extract_v4`, `ledger_v1`, `review_v1`, confidence threshold 0.7. Corpus: 12 synthetic documents in this split; one document is 8.3 % of a figure, so read the numbers as a rough guide.

| Setup | Field acc. | Exact-doc | Status acc. | Sec/doc | API calls/doc |
|---|---|---|---|---|---|
| Gemini, reading A only | 100.0 % (148/148) | 100.0 % (12/12) | 100.0 % (12/12) | 39.7 | 2.00 |
| Gemini, A + B on doubt | 100.0 % (148/148) | 100.0 % (12/12) | 100.0 % (12/12) | 39.7 | 2.00 |
| Gemini, A + B always | 100.0 % (148/148) | 100.0 % (12/12) | 100.0 % (12/12) | 58.9 | 3.00 |

### Gemini, reading A only (`SECOND_READING=never`)

Documents evaluated: **12**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 100.0 % (148/148) |
| Line-item accuracy | 86.7 % (26/30) |
| Exact-document match (required fields) | 100.0 % (12/12) |
| Status accuracy | 100.0 % (12/12) |
| Error-code recall (expected codes found) | 100.0 % (2/2) |
| Error-code precision (found codes expected) | 100.0 % (2/2) |
| Ledger accuracy | 91.7 % (11/12) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (48/48) |
| Seconds per document (model time of its calls) | 39.7 |
| API calls per document | 2.00 |
| Tokens per document | 5,734 |
| Second reading ran on | 0/12 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 100.0 % (10/10) |
| buyer_name | 100.0 % (10/10) |
| cgst | 100.0 % (12/12) |
| igst | 100.0 % (12/12) |
| invoice_date | 100.0 % (12/12) |
| invoice_number | 100.0 % (12/12) |
| place_of_supply | 100.0 % (10/10) |
| round_off | 100.0 % (12/12) |
| sgst | 100.0 % (12/12) |
| taxable_value | 100.0 % (10/10) |
| total | 100.0 % (12/12) |
| vendor_gstin | 100.0 % (12/12) |
| vendor_name | 100.0 % (12/12) |

Documents that differ from the manifest:

- `10-scan-quality.png` (test): status ready (want ready); line 1: description got 'Menu card printing,laminat d' want 'Menu card printing, laminated'
- `12-restaurant-receipt.jpg` (test): status ready (want ready); line 3: description got 'Gulab jamun （2 pc）' want 'Gulab jamun (2 pc)'
- `21-low-resolution-scan.png` (test): status ready (want ready); line 1: description got 'Postpaid business lans Oct 2026' want 'Postpaid business plans, Oct 2026'; line 2: description got 'Dataaddonpack,Oct2026 5pack' want 'Data add-on pack, Oct 2026', quantity got None want '5'
- `28-cafe-receipt.jpg` (test): status ready (want ready); ledger differs

Worst fields (wrong values, one example each):

- none

### Gemini, A + B on doubt (`SECOND_READING=on_doubt`)

Documents evaluated: **12**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 100.0 % (148/148) |
| Line-item accuracy | 86.7 % (26/30) |
| Exact-document match (required fields) | 100.0 % (12/12) |
| Status accuracy | 100.0 % (12/12) |
| Error-code recall (expected codes found) | 100.0 % (2/2) |
| Error-code precision (found codes expected) | 100.0 % (2/2) |
| Ledger accuracy | 91.7 % (11/12) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (48/48) |
| Seconds per document (model time of its calls) | 39.7 |
| API calls per document | 2.00 |
| Tokens per document | 5,734 |
| Second reading ran on | 0/12 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 100.0 % (10/10) |
| buyer_name | 100.0 % (10/10) |
| cgst | 100.0 % (12/12) |
| igst | 100.0 % (12/12) |
| invoice_date | 100.0 % (12/12) |
| invoice_number | 100.0 % (12/12) |
| place_of_supply | 100.0 % (10/10) |
| round_off | 100.0 % (12/12) |
| sgst | 100.0 % (12/12) |
| taxable_value | 100.0 % (10/10) |
| total | 100.0 % (12/12) |
| vendor_gstin | 100.0 % (12/12) |
| vendor_name | 100.0 % (12/12) |

Documents that differ from the manifest:

- `10-scan-quality.png` (test): status ready (want ready); line 1: description got 'Menu card printing,laminat d' want 'Menu card printing, laminated'
- `12-restaurant-receipt.jpg` (test): status ready (want ready); line 3: description got 'Gulab jamun （2 pc）' want 'Gulab jamun (2 pc)'
- `21-low-resolution-scan.png` (test): status ready (want ready); line 1: description got 'Postpaid business lans Oct 2026' want 'Postpaid business plans, Oct 2026'; line 2: description got 'Dataaddonpack,Oct2026 5pack' want 'Data add-on pack, Oct 2026', quantity got None want '5'
- `28-cafe-receipt.jpg` (test): status ready (want ready); ledger differs

Worst fields (wrong values, one example each):

- none

### Gemini, A + B always (`SECOND_READING=always`)

Documents evaluated: **12**.

| Metric | Result |
|---|---|
| Field accuracy (all fields) | 100.0 % (148/148) |
| Line-item accuracy | 86.7 % (26/30) |
| Exact-document match (required fields) | 100.0 % (12/12) |
| Status accuracy | 100.0 % (12/12) |
| Error-code recall (expected codes found) | 100.0 % (2/2) |
| Error-code precision (found codes expected) | 100.0 % (2/2) |
| Ledger accuracy | 91.7 % (11/12) |
| Provenance hit rate (proxy: cited words hold the true value) | 100.0 % (48/48) |
| Seconds per document (model time of its calls) | 58.9 |
| API calls per document | 3.00 |
| Tokens per document | 8,337 |
| Second reading ran on | 12/12 documents |
| **Safety invariant** (no blocking error ends `ready`) | **holds, 0 violations** |

Per field:

| Field | Accuracy |
|---|---|
| buyer_gstin | 100.0 % (10/10) |
| buyer_name | 100.0 % (10/10) |
| cgst | 100.0 % (12/12) |
| igst | 100.0 % (12/12) |
| invoice_date | 100.0 % (12/12) |
| invoice_number | 100.0 % (12/12) |
| place_of_supply | 100.0 % (10/10) |
| round_off | 100.0 % (12/12) |
| sgst | 100.0 % (12/12) |
| taxable_value | 100.0 % (10/10) |
| total | 100.0 % (12/12) |
| vendor_gstin | 100.0 % (12/12) |
| vendor_name | 100.0 % (12/12) |

Documents that differ from the manifest:

- `10-scan-quality.png` (test): status ready (want ready); line 1: description got 'Menu card printing,laminat d' want 'Menu card printing, laminated'
- `12-restaurant-receipt.jpg` (test): status ready (want ready); line 3: description got 'Gulab jamun （2 pc）' want 'Gulab jamun (2 pc)'
- `21-low-resolution-scan.png` (test): status ready (want ready); line 1: description got 'Postpaid business lans Oct 2026' want 'Postpaid business plans, Oct 2026'; line 2: description got 'Dataaddonpack,Oct2026 5pack' want 'Data add-on pack, Oct 2026'
- `28-cafe-receipt.jpg` (test): status ready (want ready); ledger differs

Worst fields (wrong values, one example each):

- none

Live calls made in this run: 0. Run time 67 s.
