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

### Slice 16: Duplicate keys and the duplicate rules  (milestone M2)

- **Outcome:** `backend/app/validation/duplicates.py`.
  - `invoice_key(invoice)` = vendor GSTIN + invoice number + financial year. `receipt_key(receipt)` = merchant + date + total.
  - The invoice number and merchant are compared ignoring case and punctuation (`INV/26-27/001` equals `inv-26-27-001`); leading zeros still count (`INV-001` is not `INV-1`). A receipt total compares by value (`1176` equals `1176.00`).
  - A key is `None` until every part is known and settled: no GSTIN / number / merchant / total, or a date that is missing, unreadable or ambiguous. A half-known key would match too much.
  - `invoice_duplicate_issue` / `receipt_duplicate_issue` take `existing: {document_id: key}` and return `DUPLICATE_INVOICE` / `DUPLICATE_RECEIPT` (blocking) naming the first matching document. `validate_invoice` and `validate_receipt` got an optional `existing` argument.
  - `key.text` gives a stable string (`invoice|<gstin>|<number>|2026-27`, `receipt|<merchant>|<date>|<total>`).
- **Why:** The same bill paid twice, or booked twice, is a real accounting error. The rules stay pure: the caller supplies the existing keys.
- **For M3 (service):** pass the keys of this client's other documents, leave out the document itself and records that are rejected or failed, so a corrected re-issue of a rejected bill is not blocked. `docs/architecture.md` lists three invoice key columns (`norm_vendor_gstin`, `norm_invoice_number`, `financial_year`) and none for receipts; one `duplicate_key` string column holding `key.text` would cover both kinds. That is a schema choice for M3, not made here.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 244 tests (19 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # also checks duplicates on the samples
  ```

- **Result:** 244 tests pass; ruff clean. On the 12 cached samples the keys are all unique and complete, and uploading any sample again is flagged as a duplicate of exactly itself: 12/12. No API calls, no new dependencies.
- **Checkpoint:** `rules_samples.py` ends with `DUPLICATES keys unique: True; re-upload flagged against itself: 12/12`.

Risk: dropping punctuation could make two different numbers equal (`A-1/2` and `A12`). That is rare, the issue is shown with the other document's id, and the reviewer decides; the alternative (exact match) would miss the common re-typed or OCR-spaced duplicate.

Important locations: `backend/app/validation/duplicates.py`, `backend/tests/test_duplicates.py`.

### Slice 17: Confidence caps and review status  (milestone M2)

- **Outcome:** two modules and one fix.
  - `validation/confidence.py`: `apply_format_caps(fields)` returns a copy where a value that fails its own format has confidence at most 0.3 (policy-rules.md): an invalid GSTIN, a date that is not a real date, an amount that is not a number (including line-item and tax-row cells). It never raises a confidence. An ambiguous date is still a readable date, so it is not capped (it already has its own blocking issue).
  - `validation/review.py`: `review_document(document, fields, client, today, threshold, existing)` is the whole validation step in one pure call: format caps, then `validate_invoice` / `validate_receipt`, then tidy-up, then the status. It returns `ReviewResult(status, issues, fields)`.
  - Status: `ready` = no blocking error and every required field is grounded and at or above the threshold (0.80); otherwise `needs_review`. (`processing`, `failed`, `approved`, `rejected` belong to the pipeline and the human.) Required fields: vendor name, vendor GSTIN, invoice number, date, total for invoices; merchant, date, total for receipts.
  - Tidy-up: blocking errors first; and no `LOW_CONFIDENCE_FIELD` on a field that already has an error, because the format cap would otherwise report an invalid GSTIN twice.
- **Fix to slice 14:** for receipts I had treated a printed GSTIN as a required field for confidence. Policy says only merchant, date and total are required, and the manifest expects the phone-photo fuel receipt (GSTIN OCR confidence 0.71) to be `ready`. Now a printed GSTIN still has to be found on the page (a made-up one must not slip through; `UNGROUNDED_REQUIRED_FIELD`) and must be valid if printed, but a low confidence on it is no warning and does not change the status.
- **Why:** M3's pipeline step then needs only this one call for its validation stage, and the status rule lives in one tested place.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest                                  # 267 tests (23 new)
  uv run --locked --no-sync python ../playground/rules_samples.py   # all 12 documents: errors, status, duplicates
  ```

- **Result:** 267 tests pass; ruff clean. On all 12 cached samples, both the blocking codes and the status equal the manifest: 12/12 (eight `ready`, four `needs_review`: 05, 06, 07, 08). Keys unique and re-upload flagged: 12/12. The fuel receipt is `ready` with one warning, `missing_tax_breakup`. No API calls, no new dependencies.
- **Checkpoint:** `rules_samples.py` ends with `AGREE 12/12 documents (errors and status)`.

Not built yet: the cap of 0.5 for two readings that disagree (needs the second reading, M3). `READINGS_DISAGREE` and `DUPLICATE_FILE` are also added by the pipeline.

Important locations: `backend/app/validation/confidence.py`, `backend/app/validation/review.py`, `backend/tests/test_confidence.py`, `backend/tests/test_review.py`.

### Slice 18: Prompt `extract_v2` (dev split only), and M2 wrap-up  (milestone M2)

- **Outcome:**
  - `providers/prompts/extract_v2.md` = v1 plus two rules. (4) On a receipt every purchased item row is a line item even without a table (a fuel row, each dish); fill only what is printed on that row; never turn a total, tax or payment row into a line item. (6) `vendor_name` is the business name only; stop before address words, phone numbers, taglines and labels. Both are written generally; no sample name or address is in the prompt.
  - `extract(document, settings, prompt_version)` takes the prompt version (recorded in `CallInfo`); **`EXTRACT_PROMPT` is now `extract_v2`**.
  - `playground/extract_samples.py`: `--prompt`, `--split dev`. One cache folder per prompt (`extract_v1` stays in `output/extract/`, which the offline scripts read; others go to `output/<prompt>/`). A model call on a test-split document is refused unless `--allow-test` (reserved for the final evaluation); cached results can still be read.
  - `playground/compare_prompts.py`: v1 against v2 on the dev split, offline (fields, ungrounded count, line items, status, errors, tokens).
- **Why:** the two weaknesses seen in slice 5 that a prompt can fix. Prompts are tuned on the dev split only (`docs/evaluation.md`).
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python ../playground/extract_samples.py all --prompt extract_v2 --split dev --fresh   # 7 API calls (done once)
  uv run --locked --no-sync python ../playground/compare_prompts.py extract_v1 extract_v2                       # offline
  ```

- **Live calls used:** 7 (`gemini-3.5-flash-lite`, one per dev document: 01, 03, 05, 07, 08, 09, 11), about 4,000 input tokens each, 8,800 for the two-page invoice.
- **Result (dev split, 7 documents, one run each):**

  | | `extract_v1` | `extract_v2` |
  |---|---|---|
  | Fuel receipt (11): line items / fields | 0 / 6 of 7 | **1 / 7 of 7** |
  | Other six dev documents: status and blocking codes | as in the manifest | identical |
  | Values still ungrounded after grounding | 0 | 0 |
  | Review status vs manifest | 7/7 | 7/7 |

  Sample 03: v2 printed the place of supply as "Madhya Pradesh" where v1 had "Madhya Pradesh (23)". The playground's rough scorer counts that as wrong; the real normaliser reads both as state 23, so it is not a regression. Vendor names were identical in v1 and v2 on all dev documents. v2 costs about 3 % more input tokens (the longer prompt).
- **What this does not show:** the vendor-name problem was seen on sample 02, which is in the **test** split, and no dev document has the problem, so rule 6 could not be checked and nothing is claimed for it. Its effect is measured in M5 on the test split. Results are from one run; model output varies a little between runs (see the sample 03 spelling).
- **Checkpoint:** `compare_prompts.py extract_v1 extract_v2` prints `lines 0 -> 1` and `fields 6/7 -> 7/7` for `11-fuel-receipt.jpg`, and no other difference in status or errors.

#### M2 summary

Everything in M2 is pure code with 267 offline tests (ruff clean), and no model call is needed to run them.

| Slice | What |
|---|---|
| 6 | Typed models: grounded field, normalised invoice / receipt, issues |
| 7 | Grounding with row-based re-pointing (489 of 489 values grounded on the 12 samples) |
| 8 | Normalisation: amounts, day-first dates (ambiguous flagged), GSTIN, state codes |
| 9 | GSTIN validation with a fix suggestion |
| 10 | Tax split, totals, dated GST slab table |
| 11 | Date checks and the financial year |
| 12-13 | Invoice rules (header, then money and lines) |
| 14 | Receipt rules |
| 15 | Amount in words (lakh / crore) |
| 16 | Duplicate keys and rules |
| 17 | Confidence caps and review status (`review_document`) |
| 18 | `extract_v2` |

On the 12 cached samples the whole chain gives the manifest's blocking codes and status on 12/12, with no API call (`rules_samples.py`).

**Moved to M3** (they need pipeline pieces): `READINGS_DISAGREE` and the 0.5 confidence cap (second reading); `DUPLICATE_FILE` (SHA-256 of the file); loading `existing` duplicate keys from the repository. 27 of the 29 issue codes in `policy-rules.md` are produced by rules; these are the other two.

**Still to verify by you:** the GST state table (`normalisation/states.py`) and the rate-slab table (`validation/tax_slabs.py`) are written from the policy text and memory, not from the official lists. Both are marked in the code.

Important locations: `backend/app/providers/prompts/extract_v2.md`, `backend/app/providers/__init__.py`, `playground/extract_samples.py`, `playground/compare_prompts.py`.

### Slice 19: Pipeline skeleton: reading, extraction, grounding, validation  (milestone M3)

- **Outcome:**
  - `pipeline/base.py`: `PipelineContext` (file bytes, client, settings, an injectable `extractor`, and the results of each step), a `Step` protocol, `run_pipeline(steps, context)` and a per-step timing trace. A step that cannot continue raises `PipelineError`; the run stops and returns the message (the document will become `failed`).
  - `pipeline/steps.py`: `ReadingStep`, `ExtractionStep`, `GroundingStep` (grounding + normalisation), `ValidationStep` (`review_document`), and `build_default_pipeline()`. An unsupported file, a file with no readable words, or a document the model classes as `other` stops the run with a clear message.
  - `playground/pipeline_samples.py`: runs the whole pipeline on all 12 samples, with the cached reading-A output as the extractor.
- **Why:** M3's service and routes need one object that runs file -> reviewed document. The extractor is passed in, so the same pipeline runs offline for checks and with Gemini in the app. Steps decide no policy; the rules stay in `validation/`.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python ../playground/pipeline_samples.py
  uv run --locked --no-sync ruff check app scripts ../playground
  uv run --locked --no-sync pytest
  ```

- **Result:** 12/12 samples give the manifest's status and blocking codes through the pipeline (eight `ready`, four `needs_review`). Reading takes 15-60 ms for PDFs and 2.5-7 s for OCR images; the other steps take about 1-10 ms. Ruff clean, 267 tests pass. No API calls, no new dependencies.
- **Checkpoint:** `pipeline_samples.py` ends with `AGREE 12/12 documents (status and errors)`.

Not built yet: second reading + merge, ledger suggestion, caching by SHA-256, `DUPLICATE_FILE` (next slices of M3). No pytest was added: the pipeline wiring is not a pure module (CLAUDE.md), so the offline playground run is its check.

Important locations: `backend/app/pipeline/base.py`, `backend/app/pipeline/steps.py`, `playground/pipeline_samples.py`.

### Slice 20: SHA-256 reading cache and `DUPLICATE_FILE`  (milestone M3)

- **Outcome:**
  - `reader/cache.py`: `sha256_hex(data)` and `ReadingCache(directory)`. A reading (`ReadDocument` JSON) is stored under the file's SHA-256, so the same bytes are never OCR-ed twice. A damaged or outdated entry counts as a miss. `reader.render_images(data)` renders only the page images (cheap, no OCR) for a cache hit.
  - `PipelineContext` now has `sha256`, `reading_cache`, `known_files` (`{sha256: document id}`, filled by the service later) and `cache_hit`. `ReadingStep` uses the cache; an empty reading is never cached.
  - `validation/duplicates.py`: `duplicate_file_issue(sha256, known_files)` gives the `DUPLICATE_FILE` warning. `ValidationStep` adds it; as a warning it does not change the status.
- **Why:** OCR takes 2.5-7 s per image, and the policy wants a re-upload flagged. Both only need the file hash.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest
  uv run --locked --no-sync python ../playground/pipeline_samples.py
  ```

- **Result:** 268 tests pass (1 new); ruff clean. Cached words equal a fresh read on 12/12 samples; reading for all 12 takes 456 ms with the cache (about 17 s cold). Re-uploading each sample flags `duplicate_file` exactly once on 12/12 and leaves the status unchanged. No API calls, no new dependencies.
- **Checkpoint:** `pipeline_samples.py` prints `CACHE hits 12/12 ...` and `DUPFILE flagged once on re-upload 12/12; status unchanged 12/12`.

Notes: the cache folder (planned under `backend/data/`, git-ignored) is wired in by the service later. Delete it after any change to the reader. The "skip the document itself, rejected and failed records" part of `known_files` / `existing` needs the repository and stays open.

Important locations: `backend/app/reader/cache.py`, `backend/app/pipeline/steps.py`, `backend/tests/test_duplicates.py`.

### Slice 21: Ledger catalog  (milestone M3)

- **Outcome:** `accounting/catalog.py` holds the 13 fixed ledgers from `policy-rules.md` (`Ledger(code, name, typical)`, `LEDGERS`, `LEDGERS_BY_CODE`). `checked_ledger_code(code)` returns the code only if it is in the catalog (spaces trimmed), otherwise `None`. `catalog_for_prompt()` gives one `code | name | typical bills` line per ledger for the suggestion prompt.
- **Why:** the model may only choose from this list, and code must be able to reject anything else before the suggestion is stored or approved. The catalog is fixed code, not a model output or an env setting.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest tests/test_catalog.py
  uv run --locked --no-sync ruff check app scripts tests ../playground
  ```

- **Result:** 271 tests pass (3 new); ruff clean. No API calls, no new dependencies.
- **Checkpoint:** `test_checked_ledger_code_accepts_only_catalog_codes` passes (`9999`, `Rent`, `6130.0`, empty and `None` are all rejected).

Not built yet: the suggestion prompt and step (the LLM call, with the code check on its answer), `GET /api/accounting/ledgers`. Both come in the next slices.

Important locations: `backend/app/accounting/catalog.py`, `backend/tests/test_catalog.py`.

### Slice 22: Ledger suggestion prompt and step  (milestone M3)

- **Outcome:**
  - `providers/prompts/ledger_v1.md`: pick one code from the catalog, decide from the items first and the vendor second, use the buyer's business to tell food for a restaurant from a meal for staff, fall back to miscellaneous, one-sentence reason, document text is untrusted data.
  - `providers.suggest_ledger(document, client_name, settings)`: one call. The input is only the normalised fields (buyer, vendor or merchant, item descriptions, HSN/SAC, amounts, total) plus the `<catalog>`; no raw file text. Returns `LedgerResult(choice, call)`; the prompt version is recorded in `CallInfo`.
  - `schemas/ledger.py`: `LedgerChoice` (model output) and `LedgerSuggestion` (after the check).
  - `LedgerStep`: runs after validation. The code is checked with `checked_ledger_code`; if it is not in the catalog the suggestion keeps no code and says so, and the reviewer picks. `PipelineContext` now has `ledger_suggester` (injected, like the extractor), `ledger` and `ledger_call`.
  - `playground/ledger_samples.py`: scores the suggestion against `expected_ledger`; results cached in `output/ledger_v1/`; a new call on a test-split document is refused unless `--allow-test`.
- **Why:** the ledger is the last piece of a prepared review, and approval needs it. The model only chooses among fixed codes; code decides whether the answer is acceptable.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python ../playground/ledger_samples.py --split dev   # 7 API calls (done once, then cached)
  uv run --locked --no-sync python ../playground/pipeline_samples.py             # offline
  ```

- **Live calls used:** 7 (`gemini-3.5-flash-lite`, dev documents 01, 03, 05, 07, 08, 09, 11), about 620-1,670 input and 35-46 output tokens each, 1-1.6 s each.
- **Result:** dev split **7/7** ledgers equal `expected_ledger`, each with a sensible one-line reason. The full pipeline still gives the manifest's status and errors on 12/12 offline; ruff clean, 271 tests pass.
- **What this does not show:** one run per document, on the seven dev samples, whose vendors and items are plain (stationery, laptops, AC repair, broadband, rent, groceries, fuel). It says nothing about the test split (not called yet, measured in M5), unusual bills or the invalid-code path. In `pipeline_samples.py` the five test-split documents get a labelled stand-in ledger (`6190`), so the ledger is not part of what that script compares. No pytest: the step needs a model.
- **Checkpoint:** `ledger_samples.py --split dev` prints `LEDGER 7/7 match expected_ledger` from the cache.

Not built yet: second reading + merge, `GET /api/accounting/ledgers`, storing and overriding the selected ledger (service / routes).

Important locations: `backend/app/providers/prompts/ledger_v1.md`, `backend/app/providers/__init__.py`, `backend/app/pipeline/steps.py`, `playground/ledger_samples.py`.

### Slice 23: SQLite `documents` table and repository  (milestone M3)

- **Outcome:**
  - `app/database.py`: `Base`, `create_db_engine(path)` (creates the tables; default file `backend/data/invoice_review.db`, git-ignored), `session_factory`.
  - `app/documents/models.py`: the `Document` table from `architecture.md` section 7 (client, file facts, SHA-256, status, the stage JSON columns, issues, ledger, history, pipeline run, timestamps) and the `DocumentStatus` enum. `document_type` + JSON `duplicate_key` replace the three `norm_*` columns so receipts are covered (decision D14; ER diagram updated).
  - `app/documents/repository.py`: `create`, `get`, `list(status, client_id)` (newest first), `update`, `delete`, `known_files(exclude_id)` (`{sha256: id}`, earliest upload wins) and `existing_keys(client_id, document_type, exclude_id)` (leaves out the document itself and rejected / failed records).
  - `validation/duplicates.py`: `key_to_json` / `key_from_json`, so a stored key comes back equal to the one the rules compare (1 new test).
  - `PipelineContext.existing_keys`: a loader `document type -> keys`, called by `ValidationStep` once the type is known. The service will pass the repository's method.
  - `playground/repository_samples.py`: stores the 12 pipeline results in a throw-away database and reads them back.
- **Why:** routes and the service need somewhere to keep reviews, and the two duplicate checks need data about earlier uploads. The repository holds only SQLAlchemy; the rules stay pure.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest
  uv run --locked --no-sync python ../playground/repository_samples.py
  ```

- **Result:** 272 tests pass (1 new); ruff clean. On the 12 samples: 12/12 stored with the right statuses (8 `ready`, 4 `needs_review`); filters give 8 / 4 by status and 10 / 1 / 1 by client; each document is excluded from its own duplicate checks (12/12); uploading sample 01 again gives both `duplicate_file` and `duplicate_invoice`; a rejected record stops counting; delete works. No API calls, no new dependency (SQLAlchemy was already pinned).
- **Checkpoint:** `repository_samples.py` prints `LIST 12/12 stored`, `SELF ... 12/12 file, 12/12 content`, `REUPLOAD ... duplicate_file=True duplicate_invoice=True` and `REJECTED ignored ... True`.

Not built yet: the service (upload -> pipeline -> save), upload intake, routes. `review_data`, `classification`, `extraction` and `history` columns exist but nothing fills them yet (the projection comes with the service). The repository is not covered by pytest (database access, not a pure module); the playground run is its check. There are no migrations: delete `backend/data/*.db` after a schema change.

Important locations: `backend/app/database.py`, `backend/app/documents/models.py`, `backend/app/documents/repository.py`, `playground/repository_samples.py`.

### Slice 24: Upload intake and file storage  (milestone M3)

- **Outcome:** `documents/intake.py`.
  - `check_upload(data)` decides whether a file may enter the pipeline and returns `AcceptedUpload(content_type, extension, page_count)`. The size is checked first (over 5 MB -> 413), then the type from the first bytes (not PDF, PNG or JPEG -> 415), then the page count (over 5 -> 413). A damaged or password-protected PDF -> 415.
  - A rejection is an `IntakeError` that carries its HTTP status code and a plain message, so the route only has to pass it on.
  - `new_stored_filename(ext)` gives `<uuid>.<ext>`; `save_upload(data, name)` writes it to `backend/data/uploads/` (git-ignored). The user's own file name is never used on disk, only kept as a label in the database.
- **Why:** this is the first line of defence for a file the app did not make (`security.md`). It is pure enough to test with generated PDFs and images, and it runs before any OCR or model call.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest tests/test_intake.py
  uv run --locked --no-sync python ../playground/intake_samples.py
  ```

- **Result:** 278 tests pass (6 new); ruff clean. All 12 samples are accepted with the page counts in the manifest (the two-page invoice gives 2). A renamed `.exe` gives 415, a file just over 5 MB gives 413, a damaged PDF gives 415. A 6-page PDF gives 413 (test). No API calls, no new dependency.
- **Checkpoint:** `intake_samples.py` prints `ACCEPTED 12/12 with the right page count` and three `OK` lines for the bad files.

Not built yet: the routes that turn an `IntakeError` into the response, so the `security.md` checklist lines for the renamed `.exe` and the 50-page PDF stay open until then. Not covered: a PDF with a huge page size or a decompression bomb (page size is not limited yet; rendering uses a fixed DPI and images are capped at 2,200 px, `reader/render.py`).

Important locations: `backend/app/documents/intake.py`, `backend/tests/test_intake.py`, `playground/intake_samples.py`.

### Slice 25: Document service, provider retry and the pipeline run record  (milestone M3)

- **Outcome:**
  - `providers/retry.py`: `retry_with_backoff(call, delays, is_retryable)` (pure, SDK-free) and `ProviderError(message, busy)`, the only provider error the rest of the app sees. `providers._run_agent` wraps every model call: `429` and `5xx` are retried after 4 s, 12 s and 30 s (`AppConfig.provider_retry_delays`, so 4 attempts); SDK errors are then translated into `ProviderError` (busy or not) with a generic message, never the SDK's text.
  - Pipeline: `run_pipeline` now returns the error object (`PipelineError` = the file is unusable, `ProviderError` = the model call failed). A ledger failure does **not** fail the document: the extraction is kept, the suggestion has no code and says "Ledger suggestion is unavailable ... Pick one by hand."
  - `documents/service.py`: `DocumentService.upload(data, filename, client_id)` = client check -> `check_upload` -> store `<uuid>.<ext>` -> create the row (`processing`) -> run the pipeline with `known_files` and `existing_keys` from the repository -> save. The document is always saved, also when the pipeline fails (`failed`, `error_message`). Saved: status, `document_type`, `duplicate_key`, `reading`, `extraction`, `classification`, `issues`, `ledger` (`selected_code` empty: the reviewer confirms), `history` (uploaded / processed / retry) and `pipeline_run` (provider, model, prompt versions, calls, ms per step, reading from cache, error kind). `retry(id)` re-runs a `failed` document from its stored file (`ConflictError` otherwise). Unknown client, unknown document and conflict are their own exceptions for the routes to map to 404 / 404 / 409.
  - `playground/service_samples.py`: the whole service on the 12 samples with a throw-away database.
- **Why:** this is the orchestration layer the routes call; state changes live here, not in the routes. Retrying busy providers is the free-tier behaviour from `free-tier-limits.md`.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest
  uv run --locked --no-sync python ../playground/service_samples.py
  ```

- **Result:** 283 tests pass (5 new, for the retry helper); ruff clean. Through the service all 12 samples get the manifest's status and their stored file is byte-identical; the 7 dev documents record `ledger_v1` and 2 calls. Uploading sample 01 again gives `duplicate_file` + `duplicate_invoice` and `needs_review`. A renamed `.exe` (415) and an unknown client store no row. With a busy provider the upload is saved as `failed` (error kind `provider`), retrying a non-failed document is a conflict, and retrying the failed one gives `ready`. With a failing ledger call the fuel receipt stays `ready` with no suggested code. No API calls, no new dependency.
- **What this does not show:** the real `429` path. The backoff logic is tested with plain functions, and `_is_busy` / the SDK error translation have not been exercised against a real rate-limit response (that needs live calls beyond the limit, or a fake server). The retry waits add up to 46 s inside the upload request in the worst case.
- **Checkpoint:** `service_samples.py` prints `UPLOAD status equals manifest 12/12`, `REUPLOAD file=True invoice=True`, `FAILED status=failed kind=provider` and `RETRY status=ready`.

Not built yet: the routes (the status-code mapping: `IntakeError` 413 / 415, unknown client or document 404, `ConflictError` 409, provider failure 502, "neither invoice nor receipt" 422), the projection into `review_data`, edits, the ledger selection, the decision and the approval invariant.

Important locations: `backend/app/documents/service.py`, `backend/app/providers/retry.py`, `backend/tests/test_retry.py`, `playground/service_samples.py`.

### Slice 26: HTTP routes, part 1  (milestone M3)

- **Outcome:** the read side and the upload of the API, wired in `create_app()`.
  - `GET /api/clients`, `GET /api/accounting/ledgers` (`app/reference_routes.py`).
  - `POST /api/documents` (multipart `file` + `client_id`) -> `201` with the review; `GET /api/documents` (filters `status`, `client_id`, newest first); `GET /api/documents/{id}`; `GET .../file` (original bytes, `nosniff`); `GET .../pages/{n}` (page PNG in the pixels of the word boxes); `POST .../retry`; `DELETE` (`204`, also removes the stored file).
  - Status codes: `413` / `415` from `IntakeError`, `404` unknown client, document or page, `409` retry of a document that is not `failed`, `422` bad `status` filter or a file that is not an invoice / receipt, `502` provider failure. The last two still save the document as `failed` and answer `{detail, document}`.
  - `documents/routes.py` only parses and maps; `documents/schemas.py` has `DocumentResponse` (the big `reading` and `extraction` columns are not sent); `DocumentService` gained `file_path`, `page_png` and `delete`. One database session and one service per request. Handlers are plain `def` (the reading and model calls block). The upload reads at most 5 MB + 1 byte.
  - `create_app(data_dir, extractor, ledger_suggester)`: the server passes nothing and uses `backend/data/` and Gemini; the arguments let a check use a temporary folder and cached answers.
- **Bug found while checking:** a `failed` document has no issues yet (`NULL` column), so building its response failed and the 502 / 422 answer crashed. `DocumentResponse` now turns an empty `issues` / `history` into `[]`.
- **Why:** the UI (M4) and `curl` need an HTTP surface. The routes hold no logic, so the service stays the single place for workflow.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync python ../playground/api_samples.py      # offline, TestClient
  uv run --locked --no-sync uvicorn app.main:create_app --factory --reload --port 8000   # then open http://localhost:8000/docs
  ```

- **Result:** `api_samples.py` passes 26/26 checks: health, clients (3), ledgers (13), CORS for the Vite origin, 12 uploads -> `201` with the manifest status, filters (8 `ready`, 4 `needs_review`, 10 for C001), the original file back byte for byte, page PNGs (page 2 of a one-page file is `404`), renamed `.exe` `415`, over 5 MB `413`, 6 pages `413`, unknown client `404` and nothing stored, a path in the file name never reaches the disk, busy provider `502` then retry `200 ready`, "not an invoice" `422`, delete `204` then `404`. 283 tests pass; ruff clean; the real `create_app()` starts. No API calls, no new dependency (`python-multipart` was already pinned).
- **What this does not show:** the real server was started only inside `TestClient`; open `/docs` once yourself and try an upload with Gemini (it uses live quota: 2 calls per document). The page-image route renders on every request. No password gate yet (M6), so the API is open locally.
- **Checkpoint:** `api_samples.py` ends with `API 26/26 checks passed`.

Not built yet: edit (`PUT`), ledger selection, the decision and the approval invariant, bulk approve, correction email, export. The `security.md` upload checklist lines (renamed `.exe`, 50-page PDF) now pass at the API level; they are ticked in M6 with the rest of that checklist.

Important locations: `backend/app/documents/routes.py`, `backend/app/documents/schemas.py`, `backend/app/reference_routes.py`, `backend/app/main.py`, `playground/api_samples.py`.

### Slice 27: Ledger selection, decision, bulk approve and the approval invariant  (milestone M3)

- **Outcome:**
  - `validation/approval.py` (pure): `approval_blockers(status, issues, selected_ledger_code)` returns the reasons a record cannot be approved, `rejection_blockers(status)` the same for rejecting. A record can be approved only if it is `ready`, has no blocking error in its issues, and has a selected code that is in the catalog. `approved` and `rejected` are locked. It checks the status **and** the issues, so a bad status alone could not let an error through.
  - `DocumentService.select_ledger`, `decide` and `bulk_approve` use it. `select_ledger` accepts only catalog codes (`LedgerNotFoundError` -> 404), refuses a decided record or one with no ledger step (409), stores `selected_code` and `overridden` (true when it differs from the suggestion) and a history entry. `decide` writes a `decision` history entry. `bulk_approve` runs the same check per document, keeps the order, ignores repeated ids, and returns `approved` and `skipped` with a reason each.
  - Routes: `PUT /api/documents/{id}/ledger`, `POST /api/documents/{id}/decision`, `POST /api/documents/bulk-approve` (at most 200 ids). `409` carries the reasons in `detail`.
  - The service method `list` is now `list_documents`: inside the class it hid Python's own `list` in type hints.
- **Why:** this is the safety invariant of the project (`policy-rules.md`): code, not the UI, decides that a record with errors or no ledger can never be approved, and a human decision is final.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest tests/test_approval.py
  uv run --locked --no-sync python ../playground/api_samples.py
  ```

- **Result:** 290 tests pass (7 new); ruff clean. `api_samples.py` passes 48/48 checks (22 new). Approve with no ledger `409`; unknown ledger `404`; confirm the suggestion -> not overridden, pick another -> overridden; approve ready + ledger `200`; approve again, reject after approve and change the ledger of an approved record are all `409`; a `needs_review` document with a ledger selected cannot be approved (`409`, reasons: status and `invalid_vendor_gstin`) and stays `needs_review`; a failed document cannot be approved or given a ledger; bad decision value `422`; unknown document `404`. Bulk approve of `[ready+ledger, ready no ledger, needs_review, approved, failed, unknown, repeated]` approves exactly the first and skips five with reasons. Reject works from `ready` and `needs_review`; after a rejection, uploading the same bill again gets no `duplicate_invoice` (only `duplicate_file`). No API calls, no new dependency.
- **What this does not show:** the invariant is checked through the service only; nobody has tried to bypass it with a hand-edited database row (that is outside the threat model, the file is local). Edits are not built, so the "edit a decided record" lock is not exercised yet (it comes with the edit route). Confidence of a `ready` record is trusted from the pipeline status, not recomputed at approval.
- **Checkpoint:** `api_samples.py` ends with `API 48/48 checks passed`; `tests/test_approval.py` passes.

Not built yet: the `review_data` projection and `PUT` field edit (with source `human`, re-validation, lock of decided records), correction email, export, `READINGS_DISAGREE` / second reading.

Important locations: `backend/app/validation/approval.py`, `backend/app/documents/service.py`, `backend/app/documents/routes.py`, `backend/tests/test_approval.py`, `playground/api_samples.py`.

### Slice 28: `review_data` and field edits  (milestone M3)

- **Outcome:**
  - `documents/projection.py` (pure): `build_review_data(grounded_fields)` makes the flat, editable view saved in the `review_data` column: one entry per extracted value, addressed by path (`vendor_gstin`, `line_items[2].taxable_amount`, `tax_lines[0].amount`), each with `value`, `original` (the model's reading), `source`, `confidence`, `grounding`, `agreement` (empty until the second reading) and `evidence` (page, word ids, box). `apply_edits` returns a new `review_data` plus the real changes; an edited field becomes `human`, confidence 1.0, grounded (missing when cleared). `extraction_with_values` puts the review values back into the stored extraction so normalisation and the rules read them; `grounded_fields` and `refresh_review_data` convert back (the refresh keeps `original`).
  - `DocumentService.edit(id, edits)`: refuses decided, failed or processing documents (409), applies the edits, then runs normalisation, `review_document` (format caps, all rules, duplicates against the repository) and the `DUPLICATE_FILE` warning again, and saves status, issues, `review_data`, `duplicate_key` and an `edited` history entry (`{path: {from, to}}`). An edit that changes nothing returns the document unchanged.
  - The pipeline now saves `review_data` on every processed document.
  - `PUT /api/documents/{id}` with `{ "fields": { path: text | null } }`; unknown path, over-long value or empty body -> 422 with nothing applied.
- **Why:** the reviewer must be able to correct what the model got wrong, and every correction has to go through the same rules as an extracted value. Edits do not touch the stored reading-A extraction, so the audit trail still shows what the model said.
- **Commands** (from `backend/`):

  ```powershell
  uv run --locked --no-sync pytest tests/test_projection.py
  uv run --locked --no-sync python ../playground/api_samples.py
  ```

- **Result:** 298 tests pass (8 new); ruff clean. `api_samples.py` passes 66/66 (18 new). On real samples: sample 05 (invalid vendor GSTIN) edited with the app's own one-character suggestion (`...E1ZE` -> `...E1Z7`) goes `needs_review` -> `ready`, the field is `human` / 1.0 with the original kept, then ledger + approve work end to end, and a further edit of the approved record is `409`. Sample 06 (printed total 76,138.00, true total 75,138.00): the fix removes `total_mismatch`, and the status is `ready` with the remaining `amount_in_words_mismatch` warning (the words still say 76,138). A wrong total on a ready document -> `needs_review` with `total_mismatch`; the original value back -> `ready`; clearing the invoice number -> `missing_invoice_number`; editing the vendor GSTIN, number and date of one invoice into another's -> `duplicate_invoice`. Unknown field, missing line item, over-long value and empty body are `422` and change nothing; failed and rejected documents `409`; unknown document `404`. No API calls, no new dependency.
- **Bug found by the check, in the check:** the manifest's `vendor_gstin` for sample 05 is the printed (invalid) one, so my first "fix" sent the same value and four checks failed. The test now takes the corrected GSTIN from the issue's suggestion. No application code changed for that.
- **What this does not show:** an edit is a text replacement; the box still points at the original words (there is no re-grounding of a human value, by design). Rows of a line-item table cannot be added or removed yet. Several readers editing at once are not handled (one user).
- **Checkpoint:** `api_samples.py` ends with `API 66/66 checks passed`; `tests/test_projection.py` passes.

Not built yet: correction email (eligibility + draft), export, second reading + `READINGS_DISAGREE` (fills `agreement`), password gate.

Important locations: `backend/app/documents/projection.py`, `backend/app/documents/service.py` (`edit`), `backend/app/documents/routes.py`, `backend/tests/test_projection.py`, `playground/api_samples.py`.
