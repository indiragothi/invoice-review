# Build-Along

A running log of the build, so anyone can follow it step by step. Milestones are in [roadmap.md](roadmap.md).

Each working slice adds an entry **in the same commit** as its code:

```markdown
### Slice N: <title>  (milestone Mx)

- **Outcome:** what works now
- **Why:** the reason for this step
- **Commands:** exact commands to run
- **Result:** what you should observe
- **Checkpoint:** how to confirm before moving on
```

## Log

M0 (planning docs) lives on `main`.

### Slice 1: Backend scaffold, config and health check  (milestone M1)

- **Outcome:** A FastAPI backend with pinned dependencies starts locally and answers `GET /health` with the active LLM provider and model.
- **Why:** Every later step reads keys and model names through one settings module. Proving it first means a missing key fails loudly at startup instead of deep inside the pipeline.
- **Commands** (from `backend/`):

  ```powershell
  uv sync --locked
  Copy-Item .env.example .env        # first time only, then add GEMINI_API_KEY and GEMINI_MODEL
  uv run --locked --no-sync uvicorn app.main:create_app --factory --reload --port 8000
  ```

  In a second terminal:

  ```powershell
  curl.exe http://localhost:8000/health
  ```

- **Result:** `{"status":"ok","llm_provider":"gemini","model":"gemini-3.5-flash-lite"}`. Swagger UI at http://localhost:8000/docs. With `GEMINI_API_KEY` removed, startup fails with `LLM_PROVIDER=gemini needs GEMINI_API_KEY in backend/.env`.
- **Checkpoint:** `uv run --locked --no-sync ruff check app` passes; `/health` shows your model; the API key never appears in any response or log.

Important locations: `backend/pyproject.toml` (pins, 7-day cooldown), `backend/.python-version` (3.12), `backend/app/config.py` (`Settings` from `.env`, fixed `AppConfig`), `backend/app/main.py` (`create_app` factory, CORS, `/health`).

### Slice 2: Frontend scaffold talking to the backend  (milestone M1)

- **Outcome:** A Vite + React + strict TypeScript + Tailwind app on port 5173 that calls the backend `/health` and shows "Backend connected · gemini · gemini-3.5-flash-lite", or a clear red error if the backend is down.
- **Why:** Proves the two halves can talk (URL from env, CORS) before any real screen is built, and puts the typed API client and env boundary in place from day one.
- **Commands** (from `frontend/`):

  ```powershell
  pnpm install --frozen-lockfile
  Copy-Item .env.example .env        # first time only
  pnpm dev
  ```

  Keep the backend running in another terminal (slice 1), then open http://localhost:5173.

- **Result:** Green "Backend connected" box with the model name. Stop the backend and reload: a red "Backend not reachable" box appears.
- **Checkpoint:** `pnpm exec tsc -b --pretty false`, `pnpm lint` and `pnpm build` all pass; `pnpm peers check` reports no issues.

Notes: TypeScript is pinned to 6.0 because `typescript-eslint` does not support TypeScript 7 yet; `@types/node` is pinned to 22.x to match the installed Node 22. `strict` and `noUncheckedIndexedAccess` are on.

Important locations (slice 2): `frontend/pnpm-workspace.yaml` (exact saves, 7-day release age), `frontend/src/lib/env.ts` (only reader of `import.meta.env`), `frontend/src/lib/api.ts` (typed `fetch` client), `frontend/src/components/BackendStatus.tsx`.

### Slice 3: Fictional clients and the first 12 sample documents  (milestone M1)

- **Outcome:** Three fixed clients in `backend/app/clients.py` and a generator that writes 12 fictional GST documents plus `samples/manifest.json` (ground truth) in one run: 8 clean or broken text PDFs, a two-page invoice, a degraded scan (PNG) and two phone-photo receipts (JPG).
- **Why:** Every later step (reader, extraction, validation, evaluation) needs documents whose correct answer is known. Generating files and answers together means they can never disagree, and the built-in checks guarantee each broken document has exactly one intended problem.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python -m scripts.generate_samples
  ```

- **Result:** A table of 12 files with pages and expected status; files in `samples/generated/`; `manifest.json` rewritten. Running it twice gives byte-identical files.
- **Checkpoint:** Open a few files: totals, CGST/SGST vs IGST, round off and amount-in-words agree with `manifest.json`. `ruff check app scripts` passes.

Important locations: `backend/app/clients.py`, `backend/scripts/generate_samples.py` (`build_corpus()` defines every document; `check()` asserts each scenario), `samples/README.md` (what each file tests).

### Slice 4: Reader: words with boxes from PDFs, scans and photos  (milestone M1)

- **Outcome:** `app/reader` turns any upload into page images plus numbered words (`w1`, `w2` ...) with page, line, box and confidence. Digital PDF pages use the text layer (PyMuPDF, confidence 1.0); scans, photos and image-only PDF pages use RapidOCR with character-level boxes.
- **Why:** This is the evidence layer. The LLM will cite word IDs, and code will use these boxes to highlight where each value came from. Its quality caps the accuracy of everything after it.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python ../playground/read_samples.py
  ```

- **Result:** One line per sample: text source, word count, lowest confidence, seconds, and any key value (GSTINs, invoice number, total) not found in the read text. Debug images with every box drawn are written to `playground/output/` (green = PDF text, orange = OCR, red = OCR confidence below 0.90).
- **Checkpoint:** All 12 samples show `-` in the missing column; boxes in the debug images sit on the printed words. First OCR call takes a few extra seconds to load the model.

Important locations: `backend/app/reader/__init__.py` (`read_document`), `reader/render.py` (magic-byte type check, 150 DPI rendering, EXIF-aware image loading), `reader/pdf_text.py`, `reader/ocr.py` (character grouping, weakest-character confidence), `reader/schemas.py`. See decision D13.

### Slice 5: First LLM extraction with evidence word IDs  (milestone M1)

- **Outcome:** `app/providers` calls Gemini (`gemini-3.5-flash-lite`) through pydantic-ai with a strict schema (`app/schemas/extraction.py`) and a versioned prompt (`providers/prompts/extract_v1.md`). One call classifies the document and returns every field as printed, each with the IDs of the words it came from. Tax rows come back one per head and rate; code adds them up.
- **Why:** This is reading A, the core of the pipeline. Evidence IDs are what make provenance and hallucination checks possible.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python -m scripts.check_gemini                      # 1 API call
  uv run --locked --no-sync python ../playground/extract_samples.py 1 --show    # 1 call, prints JSON
  uv run --locked --no-sync python ../playground/extract_samples.py all         # 1 call per uncached doc
  ```

  Outputs are cached in `playground/output/extract/`; add `--fresh` to call the model again.

- **Result (2026-10-31, all 12 samples, prompt `extract_v1`):** type 12/12, fields 154/158 (97.5 %), values contained in their cited words 482/489. About 4,000 input tokens and 3 s per one-page document; the 34-line two-page invoice took 8.6k + 6k tokens and 12.5 s.
- **Checkpoint:** `check_gemini` prints `OK: structured output works.`; `extract_samples.py 1` shows `fields 14/14`.

What went wrong, and where it will be handled:

| Sample | Problem | Handled in |
|---|---|---|
| 02 | Vendor name took the next word of the address ("... Grains Shop") | Second reading / review; prompt v2 |
| 04 | Place of supply returned as "Karnataka" without "(29)" | Normalisation: map state names to codes (M2) |
| 08, 09 | Correct value, but evidence ID off by one word on 7 values | Grounding: search the cited line before flagging (M2) |
| 10 | OCR lost spaces: "RestaurantPvtLtd" | Name comparison ignoring spaces; reviewer sees it (M2) |
| 11 | Fuel receipt: the "Diesel 42.5 L x 92.36" row was not returned as a line item | Prompt v2: purchase rows on receipts are line items |

Note: this exploratory run included test-split documents. From now on prompts are tuned on the dev split only (see `docs/evaluation.md`).

Important locations: `backend/app/providers/__init__.py` (`build_model`, `format_words`, `extract`), `backend/app/schemas/extraction.py`, `backend/app/providers/prompts/extract_v1.md`, `backend/scripts/check_gemini.py`, `playground/extract_samples.py`.

### Slice 6: Typed models for grounded fields, documents and issues  (milestone M2)

- **Outcome:** Three small modules in `backend/app/schemas/`. `fields.py`: `GroundedField` (raw value, evidence IDs, box built by code, `grounding` = grounded / ungrounded / missing, source, confidence). `documents.py`: normalised `Invoice`, `Receipt`, `LineItem`, `TaxLine`, `NormalisedDate` (money is `Decimal`, dates are `date`, ambiguous flag kept). `issues.py`: `IssueCode` (every code in `policy-rules.md`, snake_case), `Severity`, `ValidationIssue`.
- **Why:** The pure rules in `validation/` need typed input, and grounding/normalisation need somewhere to put their output. Raw model output stays in `extraction.py`; these are what code works on after checking it.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync ruff check app scripts ../playground
  uv run --locked --no-sync python -c "from app.schemas.documents import Invoice; print(Invoice().model_dump_json())"
  ```

- **Result:** ruff passes; models import and serialise. No API calls, no new dependencies.
- **Checkpoint:** `Invoice()` prints with all fields null and `invoice_date.ambiguous` false.

Design notes: `ValidationIssue` has no `supplier_fixable` yet; it is derived from the fixed eligibility set in M3 (`correction_email/eligibility.py`). `suggestion` carries things like a one-character GSTIN fix.

Important locations: `backend/app/schemas/fields.py`, `documents.py`, `issues.py`.

### Slice 7: Grounding: check values against the cited words  (milestone M2)

- **Outcome:** `backend/app/pipeline/grounding.py`. `ground_extraction(extraction, document)` turns every value the model returned (fields, line-item cells, tax rows) into a `GroundedField`: `grounded` (box = union of the real word boxes, trimmed to the smallest run of words that holds the value), `ungrounded` (not found: confidence 0, no box) or `missing` (null). Confidence is 1.0 for the PDF text layer and the mean word confidence for OCR. Comparison ignores spaces and case, so OCR text like "RestaurantPvtLtd" still matches.
- **Re-pointing:** if the cited words do not contain the value, look for it as a **whole word** (or run of whole words), first along the same visual row, then among the 2 words either side in reading order, and take the match nearest the cited word. A fragment never counts ("9" is not found inside "1,980").
- **Why:** This is the hallucination check and the source of provenance boxes. Code verifies the model's claim; the model never draws a box.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                      # 12 grounding tests
  uv run --locked --no-sync python ../playground/ground_samples.py      # offline, uses the cached extractions
  ```

- **Result (all 12 samples, cached `extract_v1` output, no API calls):** 489 values grounded, 0 ungrounded, 15 missing (null fields). 7 values were re-pointed, all in samples 08 and 09 and all correct. Without re-pointing, 6 values in sample 09 were ungrounded. 12 tests pass; ruff clean.
- **Checkpoint:** `ground_samples.py` ends with `TOTAL {'grounded': 489, 'ungrounded': 0, 'missing': 15, 'repointed': 7}`.

What I found: the reader gives nearly every table cell its own `line` number, so "same line" cannot use `line`. A row is found by vertical overlap of the word boxes instead. In sample 09 the cited word was sometimes the first word of the next row (the serial number), hence the reading-order fallback.

Known limit: a wrong number that also appears whole next to the cited word would be accepted (for example a rate "18" in the neighbouring cell). It is the nearest match and the reviewer sees the box, but the second reading (M3) is the real guard.

Important locations: `backend/app/pipeline/grounding.py`, `backend/tests/test_grounding.py`, `playground/ground_samples.py`.

### Slice 8: Normalisation: amounts, dates, GSTIN, state codes  (milestone M2)

- **Outcome:** `backend/app/normalisation/`. `amounts.py`: `"₹ 1,23,456.00"` -> `Decimal`, brackets and minus are negative, `"9%"` -> `Decimal("9")`. `dates.py`: day-first (DD-MM-YYYY, `/`, `.`, `21 Aug 2026`, `April 25, 2025`); a numeric date where day and month could swap (04/05/2025) gets `ambiguous=True` with the day-first reading kept as the suggestion, never silently guessed. `text.py`: GSTIN upper-cased and unspaced, whitespace collapsed. `states.py`: state name or code -> 2-digit GST code ("Karnataka" -> 29, "Madhya Pradesh (23)" -> 23; a name and code that disagree give None). `assemble.py`: `normalise_extraction()` turns an `Extraction` into a typed `Invoice` or `Receipt` (None for "other").
- **Why:** Rules compare numbers, dates and state codes. They cannot do that on printed strings.
- **Small model change:** `NormalisedDate` now has `raw`, so rules can tell "date not printed" (`raw` None) from "date unreadable" (`raw` set, `value` None).
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                         # 64 tests (12 grounding + 52 normalisation)
  uv run --locked --no-sync python ../playground/normalise_samples.py      # offline, cached extractions vs manifest.json
  ```

- **Result:** 64 tests pass; ruff clean. On the 12 cached samples every compared value matches the manifest (total, taxable value, CGST / SGST / IGST totals, date, GSTINs, place of supply; 100/100, a few of those are trivial zeros for tax heads a document does not have). No ambiguous dates among the samples. No API calls, no new dependencies.
- **Checkpoint:** `normalise_samples.py` ends with `TOTAL 100/100`.

Limits and notes:
- The state table (`states.py`) is written from memory of the GST list. **Verify it against the official list** (as with the slab table). It includes 26 (merged Dadra / Daman), 97 and 99; the old Daman and Diu code 25 is not included.
- An ambiguous date is not yet settled by other dates on the document ("unless the layout or other dates settle it"). Today every such date stays flagged; the reviewer decides.
- An amount that cannot be parsed becomes None; the original text stays in the matching `GroundedField.raw`.
- `reverse_charge` is not extracted yet (no field in `Extraction`); it stays False.

Important locations: `backend/app/normalisation/`, `backend/tests/test_normalisation.py`, `playground/normalise_samples.py`.

### Slice 9: GSTIN validation with a fix suggestion  (milestone M2)

- **Outcome:** `backend/app/validation/gstin.py`. `check_gstin(gstin)` returns `GstinCheck(valid, problem, suggestion)`. Problems, checked in this order: `length` (not 15), `format` (pattern, 13th character not `0`, 14th character `Z`), `state` (first two digits), `pan` (the 10-character PAN part), `checksum` (Luhn mod 36). It works offline and does not say whether the GSTIN is active.
- **Suggestion (never applied by code):** (1) a look-alike swap `0/O`, `1/I`, `5/S`, `8/B`, only when exactly one swap makes the number valid; (2) otherwise, if only the checksum fails, the check character the first 14 characters call for. A wrong-length number gets no suggestion.
- **Why:** `INVALID_VENDOR_GSTIN` / `INVALID_BUYER_GSTIN` need a yes / no and a reason; demo document 2 needs a "checksum fix suggested".
- **Decision:** the state check uses our own table (`normalisation/states.py`) plus the legacy codes 25 and 28, not `python-stdnum`'s `gstin.validate`, because stdnum's list has no 38 (Ladakh), 97 or 99 and would reject those. Format, PAN and checksum still use stdnum's `pan` and `luhn`.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest      # 83 tests (19 are GSTIN)
  ```

- **Result:** 83 tests pass; ruff clean. On the 22 GSTINs in the 12 cached extractions, 21 are valid and the only failure is sample 05's vendor GSTIN `23QMRPW2963E1ZE` (`checksum`), with the suggestion `23QMRPW2963E1Z7`. No API calls, no new dependencies.
- **Checkpoint:** `check_gstin("23QMRPW2963E1ZE")` -> `valid=False, problem='checksum', suggestion='23QMRPW2963E1Z7'`.

Notes:
- Sample 05 was made by changing only the check character, which is not an OCR look-alike, so rule (1) finds nothing there and rule (2) gives the suggestion. Seven different single-character edits would also make that number valid, so the reviewer must compare with the document; the UI should say "the check character should probably be 7".
- Legacy codes 25 and 28 are accepted without a name in the table. Verify with the official state list together with `states.py`.
- Whether the buyer GSTIN equals the client's (`BUYER_NOT_CLIENT`) is a plain comparison and lives with the invoice rules.

Important locations: `backend/app/validation/gstin.py`, `backend/tests/test_gstin.py`.

### Slice 10: Tax split, totals and the dated slab table  (milestone M2)

- **Outcome:** `backend/app/validation/tax.py` and `tax_slabs.py`, pure functions on normalised values.
  - `supply_type(vendor_gstin, place_of_supply_code, buyer_gstin, client_state_code)`: intra if the vendor's state equals the place of supply; if that is not printed, the buyer GSTIN state, then the client's state (policy-rules.md). None when it cannot be told.
  - `tax_totals(tax_lines)`: sums every tax row per head (CGST / SGST / UTGST / IGST / cess); an unreadable amount sets `unreadable` instead of silently counting as 0.
  - `tax_split_problem(...)`: `igst_on_intra`, `cgst_sgst_unequal` (more than ₹1 apart; UTGST counts as the state side), `state_tax_on_inter`, or None. A document with no tax has no split problem.
  - `line_items_sum`, `invoice_computed_total` (taxable + all tax + round-off), `receipt_computed_total` (lines + tax + round-off), `differs` (more than ₹1 apart; exactly ₹1 is fine).
  - `tax_slabs.py`: `SLAB_TABLES` dated by `effective_from`; `is_valid_slab(rate, date)`. Before 22-09-2025: 0, 0.25, 1.5, 3, 5, 12, 18, 28. From 22-09-2025: 0, 0.25, 3, 5, 18, 40.
- **Why:** These are the facts behind `TAX_SPLIT_INCONSISTENT`, `TOTAL_MISMATCH`, `LINE_ITEMS_SUM_MISMATCH` and `UNUSUAL_TAX_RATE`. The invoice / receipt rules (next slices) turn them into issues with messages.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                 # 125 tests (42 new, tax + slabs)
  uv run --locked --no-sync python ../playground/tax_samples.py    # offline, cached extractions vs manifest.json
  ```

- **Result:** 125 tests pass; ruff clean. On the 12 cached samples the three tax error codes found by code equal the manifest's `expected_errors` on 12/12: sample 06 gives `total_mismatch` (computed 75,138.00 vs printed 76,138.00), sample 07 gives `tax_split_inconsistent` (IGST on a same-state supply), the other ten are clean. No API calls, no new dependencies.
- **Checkpoint:** `tax_samples.py` ends with `AGREE 12/12`.

Notes:
- **The slab table is not verified.** It is written from the policy text (the 22-09-2025 rationalisation), plus 1.5 % in the old table for cut diamonds. Check it against the official CBIC notifications. A rate outside the table is only a warning.
- A bill dated close to 22-09-2025 may legitimately use either set (transition period); today it can get a warning. Decide later whether to accept both sets for a window around that date.
- Sample 11 (fuel receipt) has no line items in the cached `extract_v1` output, so its receipt total cannot be cross-checked yet. That is the known `extract_v2` prompt item.
- Not in this slice: dates (future, old, financial year), and the rule that line GST rates are checked against the slabs (rules slice).

Important locations: `backend/app/validation/tax.py`, `backend/app/validation/tax_slabs.py`, `backend/tests/test_tax.py`, `playground/tax_samples.py`.

### Slice 11: Date checks and the financial year  (milestone M2)

- **Outcome:** `backend/app/validation/dates.py`. `date_problems(parsed, today)` returns what is wrong with a date: `missing` (not printed), `unreadable` (printed but no real date, e.g. 31-02-2026), `future` (after today; today itself is fine), `ambiguous`, or `old` (more than 12 months before today; exactly 12 months is fine). `financial_year(date)` gives `"2026-27"` (1 April to 31 March). `months_before` handles month ends (29 Feb -> 28 Feb).
- **Rules later map these:** missing -> `MISSING_INVOICE_DATE` / `MISSING_RECEIPT_DATE`, unreadable and future -> `INVALID_DATE`, ambiguous -> `AMBIGUOUS_DATE`, old -> `OLD_INVOICE` (warning). `financial_year` feeds the duplicate key.
- **Why:** `today` is passed in, so the function is pure and tests do not depend on the clock.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest      # 144 tests (19 new date tests)
  ```

- **Result:** 144 tests pass; ruff clean. The 12 cached samples (dates 14-08-2026 to 26-10-2026, checked against today = 31-10-2026) have no date problem and all fall in FY 2026-27. No API calls, no new dependencies.
- **Checkpoint:** `date_problems(parse_date("15-11-2026"), date(2026, 10, 31))` -> `["future"]`.

Decision: an ambiguous date is reported alone. Judging "future" or "old" on a day / month reading that may be wrong would give a misleading second issue; once the reviewer fixes the date, all rules run again.

Not done: settling an ambiguous date from other dates on the document (the policy allows "unless the layout or other dates settle it"); every such date is flagged for now.

Important locations: `backend/app/validation/dates.py`, `backend/tests/test_dates.py`.

### Slice 12: Invoice rules, part 1: header, GSTINs, grounding  (milestone M2)

- **Outcome:** `backend/app/validation/invoice.py` with `header_issues(invoice, fields, client, today, threshold)` and `validation/shared.py` (helpers receipts will reuse). `schemas/issues.py` gets `BLOCKING_CODES` and `make_issue()`, so the severity of every code is decided in one place.
  - Blocking: `MISSING_VENDOR_NAME`, `MISSING_INVOICE_NUMBER`, `MISSING_INVOICE_DATE`, `INVALID_DATE` (unreadable or future), `AMBIGUOUS_DATE`, `MISSING_TOTAL`, `MISSING_VENDOR_GSTIN`, `INVALID_VENDOR_GSTIN` (with the fix as `suggestion` and in the message), `INVALID_BUYER_GSTIN`, `BUYER_NOT_CLIENT`, `UNGROUNDED_REQUIRED_FIELD`.
  - Warnings: `MISSING_BUYER_GSTIN`, `INVOICE_NUMBER_TOO_LONG` (over 16), `OLD_INVOICE`, `REVERSE_CHARGE`, `LOW_CONFIDENCE_FIELD`.
  - Required fields for the grounding and confidence checks: vendor name, vendor GSTIN, invoice number, invoice date, total.
- **Why:** Rules receive plain values and return issues; they never touch files, the clock or the database. Each issue names the field it is about (`vendor_gstin`, `invoice_date`), so the UI can highlight the box.
- **Decisions:**
  - An invalid buyer GSTIN is reported as `INVALID_BUYER_GSTIN` only, not also as `BUYER_NOT_CLIENT` (its fix suggestion may point at the client).
  - A missing or ungrounded value does not also get `LOW_CONFIDENCE_FIELD`; it already has its own issue.
  - The confidence caps from policy-rules.md (GSTIN or date fails its format -> 0.3, readings disagree -> 0.5) are applied where confidence is computed, not here. Not built yet.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 164 tests (20 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # offline: ground + normalise + rules vs manifest.json
  ```

- **Result:** 164 tests pass; ruff clean. On the 10 invoices among the 12 cached samples, the blocking codes found equal `expected_errors` (for the codes built so far) on 10/10: sample 05 gives `invalid_vendor_gstin` with the suggestion `23QMRPW2963E1Z7`, sample 08 gives `buyer_not_client`, the rest are clean, and no sample raises a warning. No API calls, no new dependencies.
- **Checkpoint:** `rules_samples.py` ends with `AGREE 10/10 invoices`.

Next (part 2): money and line rules (`LINE_ITEMS_SUM_MISMATCH`, `TOTAL_MISMATCH`, `TAX_SPLIT_INCONSISTENT`, `MISSING_HSN_SAC`, `UNUSUAL_TAX_RATE`) and one `validate_invoice()` that joins both parts. Not in `invoice.py` by design: `AMOUNT_IN_WORDS_MISMATCH` (own slice), duplicates (need existing records), `READINGS_DISAGREE` and `DUPLICATE_FILE` (pipeline, M3).

Important locations: `backend/app/validation/invoice.py`, `validation/shared.py`, `backend/app/schemas/issues.py`, `backend/tests/test_invoice_header.py`, `playground/rules_samples.py`.

### Slice 13: Invoice rules, part 2: money and line rules  (milestone M2)

- **Outcome:** `amount_issues(invoice, client)` and `validate_invoice(invoice, fields, client, today, threshold)` in `backend/app/validation/invoice.py`. `validate_invoice` = header rules (slice 12) + amount rules.
  - Blocking: `TOTAL_MISMATCH` (taxable value + all tax + cess + round-off vs the total, more than ₹1 apart; the message shows both numbers), `LINE_ITEMS_SUM_MISMATCH` (line amounts vs taxable value), `TAX_SPLIT_INCONSISTENT` (IGST on a same-state supply, unequal CGST / SGST, CGST / SGST on an other-state supply).
  - Warnings, one per line, pointing at `line_items[i].hsn_sac` / `.gst_rate`: `MISSING_HSN_SAC`, `UNUSUAL_TAX_RATE` (the line's GST rate is not a slab on the invoice date; skipped when the rate or a real date is missing).
- **Decision (found by a test):** if any tax amount could not be read, the sums are wrong, so neither the split nor the total is judged. Otherwise an unreadable SGST counted as 0 would raise a false `TAX_SPLIT_INCONSISTENT`.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 182 tests (18 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # offline: ground + normalise + all invoice rules vs manifest.json
  ```

- **Result:** 182 tests pass; ruff clean. On the 10 invoices among the 12 cached samples the blocking codes equal `expected_errors` on 10/10: sample 05 `invalid_vendor_gstin`, 06 `total_mismatch`, 07 `tax_split_inconsistent`, 08 `buyer_not_client`, the other six clean; no warnings on any sample. No API calls, no new dependencies.
- **Checkpoint:** `rules_samples.py` ends with `AGREE 10/10 invoices`.

Still open for invoices: `AMOUNT_IN_WORDS_MISMATCH` (own slice), `DUPLICATE_INVOICE` (duplicate-key slice), `READINGS_DISAGREE` and `DUPLICATE_FILE` (pipeline, M3).

Important locations: `backend/app/validation/invoice.py`, `backend/tests/test_invoice_amounts.py`.

### Slice 14: Receipt rules  (milestone M2)

- **Outcome:** `backend/app/validation/receipt.py` with `validate_receipt(receipt, fields, today, threshold)`. Receipts need fewer fields: no invoice number, no buyer GSTIN, GST may be absent.
  - Blocking: `MISSING_MERCHANT`, `MISSING_RECEIPT_DATE` / `INVALID_DATE` / `AMBIGUOUS_DATE`, `MISSING_TOTAL`, `LINE_ITEMS_SUM_MISMATCH` (line amounts + tax + round-off vs the total, only if line items exist), `INVALID_VENDOR_GSTIN` (only if a GSTIN is printed), `UNGROUNDED_REQUIRED_FIELD` (merchant, date, total, and the GSTIN when printed).
  - Warnings: `MISSING_TAX_BREAKUP` (no tax rows at all), `LOW_CONFIDENCE_FIELD`.
- **Shared code:** the date, GSTIN, grounding and confidence checks come from `validation/shared.py`. `date_issues` got `warn_old`; receipts pass `False`, because policy-rules.md lists no old-bill warning for receipts.
- **Decisions:** as for invoices, an unreadable tax amount means the line-items check is skipped. A tax row with amount 0 counts as a tax breakup (the fuel slip with "GST nil" is not warned).
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 197 tests (15 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # all 12 documents: invoice and receipt rules vs manifest.json
  ```

- **Result:** 197 tests pass; ruff clean. On all 12 cached samples the blocking codes equal `expected_errors`: 12/12 (the 10 invoices as before; both receipts clean). The fuel receipt (sample 11) gets two warnings: `missing_tax_breakup`, and `low_confidence_field` on the vendor GSTIN (OCR confidence 0.71 on the phone photo, threshold 0.80). That warning is correct: a reviewer should look at it. No API calls, no new dependencies.
- **Checkpoint:** `rules_samples.py` ends with `AGREE 12/12 documents`.

Limits:
- The receipt total check assumes line amounts are before tax. A receipt whose line prices already include GST would raise a false `LINE_ITEMS_SUM_MISMATCH`. None of the 12 samples does this; watch for it in the M5 corpus.
- Sample 11 still has no line items in the cached `extract_v1` output, so its total is not cross-checked (known; `extract_v2`).
- `DUPLICATE_RECEIPT` (merchant + date + total) goes with the duplicate-key slice.

Important locations: `backend/app/validation/receipt.py`, `backend/tests/test_receipt.py`.

### Slice 15: Amount in words  (milestone M2)

- **Outcome:** `backend/app/normalisation/words.py` with `parse_amount_in_words(text)`, and the rule `AMOUNT_IN_WORDS_MISMATCH` (warning) inside `amount_issues` in `validation/invoice.py`.
  - Parser: Indian numbering (thousand, lakh / lakhs / lac, crore); `Rupees`, `Rs`, `INR`, `Only` and `and` are ignored; hyphens and commas are fine ("seventy-five"); the common misspelling "Fourty" is accepted; paise in both forms ("... and Thirty Four Paise" and "... and Paise Thirty Four"). Anything that is not a clean amount in words gives `None`.
  - Rule: the words (as a number) must be within ₹1 of the printed total. If the words cannot be read, or the total is missing, nothing is judged.
- **Why:** An invoice whose words and figure disagree is a classic error or tampering sign. Reading lakh / crore correctly matters: "One Lakh Eighteen Thousand" is 1,18,000.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 225 tests (28 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # all 12 documents, offline
  ```

- **Result:** 225 tests pass; ruff clean. As a one-off check (not committed) the parser read back the sample generator's own number-to-words for 20,023 numbers (edge cases plus 20,000 random up to 9,99,99,999) with 0 mismatches. On the 12 cached samples the 10 printed amounts in words all match their totals, so no new warning appears (`AGREE 12/12`). Sample 06 (total mismatch) correctly gets no words warning: its words equal its printed total. No API calls, no new dependencies.
- **Checkpoint:** `parse_amount_in_words("Rupees One Lakh Fifteen Thousand Five Hundred Only")` -> `Decimal("115500")`.

Limits: English words only (Hindi is M7). Receipts have no amount-in-words rule in policy-rules.md. A number written in words with a typo not in the word lists is treated as unreadable, so it is not flagged either way.

Important locations: `backend/app/normalisation/words.py`, `backend/app/validation/invoice.py`, `backend/tests/test_amount_in_words.py`.
