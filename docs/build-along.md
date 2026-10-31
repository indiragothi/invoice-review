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
