# Decision Log

Short records of decisions that shape the project. Add a new entry instead of rewriting an old one; mark the old one *Superseded*.

The reference build is Dave Ebbelaar's [e2e-invoice-review](https://github.com/daveebbelaar/e2e-invoice-review). **Default rule: do what the reference build does unless an entry here says otherwise.**

## D1. No Azure; free tools only

**Context:** The reference build uses Azure Document Intelligence + Azure OpenAI. Azure sign-up needs card verification, which is not available.
**Decision:** Local PDF text / OCR + free-tier LLM APIs (Gemini primary, NVIDIA secondary).
**Consequence:** We must build our own per-field confidence and provenance, which Document Intelligence provided. See D3.

## D2. Target user: Indian CA firm

**Context:** Same problem as the reference build (a finance person preparing documents for bookkeeping), but a generic copy adds little to a portfolio. Indian GST bills have concrete, checkable rules.
**Decision:** Build for an accounts executive at a small CA firm doing GST work. Scope otherwise matches the reference build.
**Consequence:** GSTIN checksum, tax split, buyer = client, Indian dates and number formats. Every upload is tagged with a client.

## D3. OCR + LLM with evidence pointers

**Context:** A vision LLM alone gives no reliable bounding boxes and no real confidence. The roadmap requires showing where each value came from; the reference build does not draw boxes.
**Decision:** Read words with positions (PDF text layer or OCR); the LLM returns values plus the IDs of supporting words; code verifies and builds the box.
**Consequence:** Real provenance, hallucination check, confidence from OCR. Costs a grounding step and careful normalisation ("1,23,456.00" can span several OCR words).

## D4. Classify + extract in one call; second reading on doubt

**Context:** Free-tier rate limits. The reference build uses separate calls.
**Decision:** One structured call classifies and extracts. The independent vision reading runs when a required field is ungrounded, low-confidence or missing (`SECOND_READING=on_doubt`).
**Consequence:** 2-3 calls per upload including the ledger. The evaluation must show what the second reading adds.

## D5. React + FastAPI, like the reference build

**Decision:** Vite + React + TypeScript + Tailwind frontend, FastAPI backend. Not Streamlit, not Next.js.
**Consequence:** More code, but a review screen with a page overlay that looks like a real product.

## D6. Pure modules get unit tests (deliberate difference)

**Context:** The reference build forbids test suites. Here the validation rules (GSTIN, tax maths, dates) are money logic, and the roadmap asks for real test results.
**Decision:** pytest for `validation/`, `pipeline/grounding.py` and normalisation only. Providers and UI are verified by live evaluators and a manual walkthrough, as in the reference build.
**Consequence:** Fast, offline tests where bugs cost most; no mocked LLM tests.

## D7. Background task with polling

*Superseded by D10.*

## D8. Date-aware GST slabs in config

**Context:** GST rate slabs changed from 22 September 2025.
**Decision:** Keep slabs in a dated table; an off-slab rate is only a warning.
**Consequence:** Old and new bills both handled; the table must be checked against official notifications.

## D9. pydantic-ai for all LLM calls

**Context:** The reference build already uses pydantic-ai for classification and GL suggestion. It supports Gemini and OpenAI-compatible endpoints (NVIDIA) with typed, validated output.
**Decision:** All LLM calls go through pydantic-ai agents in `providers/`. No direct `google-genai` / `openai` usage elsewhere.
**Consequence:** Same stack as the reference build; switching provider is a setting.

## D10. Simplify to the reference build's shape

**Context:** An earlier draft had seven tables and a background task. That is more than a single-user review tool needs.
**Decision:** One `documents` table with JSON stage columns (`reading`, `extraction`, `document_review`, `review_data`, `issues`, `ledger`, `history`, `pipeline_run`). The pipeline runs synchronously inside the upload request; the UI shows a processing step.
**Consequence:** Simpler code and migrations (delete the dev DB when the schema changes). Uploads take several seconds; acceptable for one user. Revisit only if the free provider is too slow.

## D11. Keep the reference build's full scope

**Decision:** Include the ledger suggestion (GL catalog equivalent), correction-email drafts (never sent), and the shared-password gate for the deployed demo.
**Consequence:** One extra LLM call per upload (ledger) and one per email draft.

## D12. Clients are fixed configuration

**Context:** The reference build has one fixed customer (Northstar). A CA firm has many clients, but client management is not the point of the project.
**Decision:** A small fixed client list in `backend/app/clients.py`. No client CRUD.
**Consequence:** `BUYER_NOT_CLIENT` works; adding a client is a code change.

## D13. OCR words come from character boxes; confidence is the weakest character

**Context:** RapidOCR returns text lines without spaces. With `return_word_box=True` it also returns a box and confidence per character. Character boxes are approximate, so a word is occasionally split in the wrong place (e.g. `GSTIN: 27Q` + `WRCA7310M1ZK` on the degraded scan), and a few lines come back without character detail.
**Decision:** Group characters into words by horizontal gap (> 0.45 × median character width); fall back to the whole line as one word when character detail is missing. A word's confidence is its lowest character confidence. Grounding must accept a value that spans several adjacent cited words (compare the joined text).
**Consequence:** One doubtful character (the `O` in a GSTIN) makes the whole value doubtful, which is what review needs. Low-confidence thresholds must be tuned on OCR documents in M5; PDF text-layer words are always 1.0.

## D14. One `duplicate_key` column instead of three `norm_*` columns

**Context:** `architecture.md` listed `norm_vendor_gstin`, `norm_invoice_number` and `financial_year` as the duplicate key. That covers invoices only; the receipt key is merchant + date + total (`policy-rules.md`).
**Decision:** The `documents` table has `document_type` and a JSON `duplicate_key` (the fields of the invoice or receipt key, see `validation/duplicates.py`), in place of the three columns. Uniqueness is not a database constraint: the rule is a blocking issue that the reviewer sees, not an insert error.
**Consequence:** The repository rebuilds the exact key objects the pure rules compare. The ER diagram in `architecture.md` is updated.
