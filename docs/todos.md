# Todos

Step-by-step checklist for the whole build. Tick a box (`- [x]`) as soon as a step is done and verified, in the same commit as the work. Milestones and exit criteria are in [roadmap.md](roadmap.md); the how-to for each finished slice goes in [build-along.md](build-along.md).

**Legend:** `- [ ]` to do · `- [x]` done · *(you)* = a step only the owner can do

## Progress

| Milestone | Status |
|---|---|
| M0 Plan | ✅ Done |
| M1 Scaffold, samples, read + extract | ✅ Done (NVIDIA check optional, open) |
| M2 Ground + validate | ✅ Done (`READINGS_DISAGREE` and `DUPLICATE_FILE` move to M3) |
| M3 Pipeline + API | ✅ Done (your manual check of `/docs` and the XLSX is open; test-split samples are left for M5) |
| M4 Review UI | 🟡 In progress (slices 1-5 done) |
| M5 Evaluation | ⬜ Not started |
| M6 Ship | ⬜ Not started |
| M7 Stretch | ⬜ Not started |

---

## M0 Plan (`main`)

- [x] Read the roadmap project, Dave's handbook and both branches of his repo
- [x] Pick the target user: Indian CA firm (Priya)
- [x] Client brief
- [x] Policy rules (GST, receipts, ledger, correction email, statuses)
- [x] Architecture with Mermaid diagrams
- [x] API and pipeline doc
- [x] Tech stack, free-tier limits, decisions, security, evaluation, roadmap
- [x] `CLAUDE.md` (root, backend, frontend)
- [x] `git init`, `main` + `development` branches, pushed to GitHub
- [x] *(you)* Check that the Mermaid diagrams render on GitHub

## M1 Scaffold, samples, read + extract (`development`)

### Accounts and keys
- [x] *(you)* Create a free Gemini API key at https://aistudio.google.com/apikey
- [ ] *(you)* Optional: create an NVIDIA API key at https://build.nvidia.com
- [x] Fill in the Gemini rows of `free-tier-limits.md` (model chosen: `gemini-3.5-flash-lite`)

### Backend scaffold
- [x] Propose backend dependencies and get approval
- [x] `backend/pyproject.toml` with exact pins, `add-bounds = "exact"`, `exclude-newer = "7 days"`, Ruff config
- [x] Pin Python 3.12 (`.python-version`) to match the Docker image
- [x] `uv sync` → `uv.lock` (verified with `uv sync --locked` and an import check)
- [x] `app/config.py` (pydantic-settings, reads `backend/.env`, fails clearly on missing keys)
- [x] *(you)* Copy `backend/.env.example` to `backend/.env` and paste the key
- [x] `app/main.py` with `create_app()` and `GET /health`
- [x] Verify: `uvicorn` starts and `/health` returns OK; `ruff check` passes
- [x] *(you)* Run the server yourself and open http://localhost:8000/health

### Frontend scaffold
- [x] Propose frontend dependencies and get approval
- [x] Vite + React + TS strict + Tailwind + ESLint project, `pnpm-workspace.yaml` cooldown settings
- [x] `pnpm install` → `pnpm-lock.yaml` (no peer dependency issues)
- [x] `src/lib/env.ts` validating `VITE_API_BASE_URL`
- [x] Verify: `tsc`, `lint`, `build` pass; page loads; backend CORS allows `localhost:5173`
- [x] *(you)* Open http://localhost:5173 and see the green "Backend connected" box

### Samples
- [x] Fixed client list (`app/clients.py`) with 3 fictional clients
- [x] `scripts/generate_samples.py` (reportlab + pillow) writing `samples/generated/` and `manifest.json` together
- [x] Synthetic GSTINs that pass the checksum, built on made-up PANs
- [x] First 12 documents: 4 clean invoices (intra + inter-state), 4 failure cases, 2 receipts, 1 two-page, 1 scan
- [x] Verify: built-in scenario checks pass; previews checked by eye; output identical across runs
- [x] *(you)* Open a few files in `samples/generated/` and compare with `manifest.json`

### Reader (playground first)
- [x] PyMuPDF: digital PDF → words with boxes
- [x] RapidOCR: image / scan → words with boxes + confidence (character boxes grouped into words, D13)
- [x] Render page images; boxes line up when drawn on the image (debug PNGs from `playground/read_samples.py`)
- [x] Reader lives in `app/reader/`; key values found on all 12 samples
- [x] *(you)* Run `playground/read_samples.py` and look at a few debug images

### Provider checks
- [x] `scripts/check_gemini.py`: one structured pydantic-ai call works
- [ ] `scripts/check_nvidia.py`: same against the NVIDIA endpoint *(needs an NVIDIA key; optional, can move to M5)*
- [x] `providers/prompts/extract_v1.md`: classify + extract + evidence word IDs, document text delimited as data
- [x] `playground/extract_samples.py` prints JSON fields with evidence IDs and scores all 12 samples (154/158 fields)
- [x] Update `build-along.md` and the Commands section of `CLAUDE.md`
- [x] **M1 exit:** one sample → words with boxes → fields with evidence IDs in the console
- [x] *(you)* Run `extract_samples.py 1 --show` and read the output

## M2 Ground + validate

- [x] Pydantic models: invoice, receipt, line item, field-with-evidence, `ValidationIssue`
- [x] Grounding: value must appear in cited words; box = union of word boxes; `ungrounded` otherwise
- [x] Grounding: when cited IDs miss by a word, search the same line and re-point (seen on samples 08, 09)
- [x] Normalisation: Indian dates (DD-MM-YYYY, ambiguous flagged), amounts (`1,23,456.00` → `Decimal`), GSTIN upper-case
- [x] Normalisation: state name → state code for place of supply ("Karnataka" → 29)
- [x] Prompt `extract_v2` (dev split only): receipt purchase rows are line items (verified on sample 11); vendor name excludes address words (written, but not verifiable on dev: the example was on test sample 02, so check it in M5)
- [x] GSTIN: format, state code, checksum, one-character fix suggestion
- [x] Tax: intra vs inter-state split, total and line-item sums with ₹1 tolerance, dated slab table
- [x] Dates: future, old invoice, financial year
- [x] Invoice rules (all blocking errors and warnings in `policy-rules.md`)
- [x] Receipt rules
- [x] Amount-in-words check (lakh / crore)
- [x] Duplicate key (vendor GSTIN + invoice number + financial year)
- [x] Status from issues (`ready` / `needs_review`)
- [x] pytest for all of the above; `ruff` clean
- [x] Update `build-along.md`
- [x] **M2 exit:** every rule implemented, tests pass offline (two warnings need pipeline pieces and are listed under M3)

## M3 Pipeline + API

- [x] `PipelineContext` and `build_default_pipeline()`
- [x] Steps: reading → extraction → grounding → document review (second reading, merge) → validation → ledger suggestion
- [x] Second reading, pieces (slice 31): reading B from images (`review_v1`), field-by-field comparison, gap fill, 0.5 caps and the `READINGS_DISAGREE` warning as pure functions, tried on the dev split
- [x] Second reading, wiring (slice 32): `DocumentReviewStep` with `SECOND_READING=always|on_doubt|never`, `document_review` and per-field `agreement` saved, a reviewer's edit or confirmation clears the disagreement
- [x] `existing` duplicate keys and `known_files` from the repository (skips the document itself; rejected and failed records ignored)
- [x] `DUPLICATE_FILE` warning (SHA-256); the repository must supply `known_files` later
- [x] Cache readings by SHA-256
- [x] Ledger catalog (`accounting/catalog.py`): 13 fixed ledgers, `checked_ledger_code` rejects anything else
- [x] Ledger suggestion prompt (`ledger_v1`) + `LedgerStep` (one LLM call over normalised fields; code checks the code)
- [x] SQLite `documents` table and repository (`database.py`, `documents/models.py`, `documents/repository.py`)
- [x] Document service (upload -> intake -> pipeline -> save; retry of a `failed` document) (`documents/service.py`)
- [x] Upload intake: magic bytes, 5 MB, 5 pages, stored as `<uuid>.<ext>` (`documents/intake.py`; the HTTP 413 / 415 responses come with the routes)
- [x] Routes, part 1: clients, ledgers, upload, list, get, file, page image, retry, delete
- [x] Routes, part 2a: ledger selection, decision (approve / reject), bulk approve
- [x] `review_data` projection (`documents/projection.py`) and field edit `PUT /api/documents/{id}`: source `human`, confidence 1.0, every rule re-run, status moves both ways, decided records locked
- [x] Approval invariant: `409` with open errors or no ledger; decided records locked (`validation/approval.py` + `DocumentService`); edits of a decided record are locked with the edit route
- [x] Correction email: fixed eligibility codes (`correction_email/eligibility.py`) + draft endpoint `POST .../correction-email` (prompt `email_v1`, dev split only)
- [x] Export: CSV / XLSX, approved only, formula-injection safe (`GET /api/export`)
- [x] Retry with backoff on `429` / 5xx (`providers/retry.py`); `failed` + provider error after retries (the HTTP `502` comes with the routes)
- [x] Pipeline run trace (provider, model, prompt versions, calls, ms per step) saved in `pipeline_run`
- [x] Verify through the running server with the real model on the **7 dev samples** (`playground/walkthrough_live.py`, 22/22 checks, 15 live calls). The 5 test-split samples are left for the M5 evaluation so that split stays untouched (decision of the owner, 2026-11-01)
- [ ] *(you)* Open `http://localhost:8000/docs`, try one upload there, and open the downloaded `approved.xlsx` in Excel (`playground/output/walkthrough/` has one from the walkthrough)
- [x] Update `build-along.md` and `api-and-pipeline.md` (kept in step with every slice; M3 summary in `build-along.md`)
- [x] **M3 exit:** upload → `ready` / `needs_review` with fields, boxes, issues, ledger; illegal approve returns `409` (shown through the running server on the dev samples)

## M4 Review UI

- [x] `src/lib/api.ts` and `types.ts` (auth calls follow the documented `/api/auth/*`; login screen and backend gate stay in M6)
- [x] UI primitives: Button, Badge, Card, Dialog, ConfirmDialog
- [x] Welcome screen
- [x] Upload step with client picker and file preview
- [x] Processing step
- [ ] *(you)* In the browser (`http://localhost:5173`): pick a client, upload one dev sample, see the processing screen and the result summary; also try a `.txt` file and a file over 5 MB
- [x] Document inbox with status / client filters (checkboxes come with bulk approve)
- [x] Review screen: page image with box overlay, click field ↔ highlight box (read-only; browser check by you is open)
- [ ] Editable fields incl. line items; source / confidence / agree-differ badges
- [ ] Issues panel (errors vs warnings, GSTIN fix suggestion)
- [ ] Ledger picker with suggestion and reason
- [ ] Approve / reject; bulk approve on the inbox
- [ ] Correction-email dialog with Copy
- [ ] Delete review; export button
- [ ] Loading, error and provider-busy states
- [ ] `tsc`, `lint`, `build` pass
- [ ] Update `build-along.md`
- [ ] **M4 exit:** manual walkthrough of the 4 demo documents works end to end

## M5 Evaluation

- [ ] Grow the corpus to 36+ (degraded variants, more failure cases, receipts)
- [ ] Assign dev / test split in `manifest.json`
- [ ] `scripts/evaluate_corpus.py`: field, line-item, exact-doc, status, error-code, ledger, provenance, time / calls
- [ ] Safety invariant check: zero violations
- [ ] Tune confidence threshold on dev only
- [ ] Experiments: second reading never / on doubt / always; Gemini vs NVIDIA
- [ ] Error analysis: ten worst fields with examples
- [ ] Results table in README
- [ ] Update `build-along.md`
- [ ] **M5 exit:** test-split results committed, safety invariant holds

## M6 Ship

- [ ] Shared-password gate (`auth/`) + login page
- [ ] Security checklist in `security.md`, every item ticked
- [ ] Dockerfile: built SPA + FastAPI in one image; runs locally
- [ ] Choose a free host; deploy with sample data only
- [ ] README: setup, screenshots, results, live URL
- [ ] *(you)* Record a 3-5 minute demo video
- [ ] Update `build-along.md`
- [ ] **M6 exit:** live URL, video, security checklist done

## M7 Stretch

- [ ] Hindi + English bills (+ samples)
- [ ] Handwritten receipts (+ samples)
- [ ] GSTR-2B reconciliation
- [ ] Tally-friendly export
- [ ] Run both providers on every document and compare
