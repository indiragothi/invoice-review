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

## D15. M5 corpus is 30 documents and Gemini only

**Context:** `evaluation.md` and `roadmap.md` asked for 36+ documents and an experiment table with an NVIDIA row. The owner wants a smaller first evaluation: 12 documents already existed, and 18 more is enough work for now; the free-tier NVIDIA key is not set up (M1 check still open).
**Decision:** The M5 corpus is **30 documents** (18 dev, 12 test), which still meets the "30+ documents" exit criterion in `client-brief.md` and `roadmap.md`. The experiment table has three rows, all Gemini: reading A only, A + B on doubt, A + B always. The NVIDIA row is postponed (before M6 or in M7). The 18 new documents are generated by `generate_samples.py` and the first 12 are byte-identical to before, so their cached readings stay valid.
**Consequence:** One document is 3.3 % of the result, so every accuracy figure in the README must say "30 synthetic documents" and is a rough guide, not a precise rate. Reaching 36+ later only means adding entries to `build_corpus()`. The duplicate case (24) is a normal invoice on its own and a duplicate only after 01 is uploaded for the same client: the manifest records this in `duplicate_of` / `expected_when_original_exists`, and the evaluation must upload in that order.

## D16. OCR words are grouped into rows after undoing the page tilt

**Context:** On a scan tilted by 4-5 degrees (sample 20) RapidOCR returned every table cell as its own line, ordered by height. The right end of a row sat 15 px higher than its middle, so the amount came before the rate and the model paired the numbers wrongly (`rate 3,600.00`, `amount 900.00`). The rules caught it (`LINE_ITEMS_SUM_MISMATCH`), but a clean bill went to review for a reading fault that code can fix.
**Decision:** `reader/rows.py` (pure) measures the tilt from the OCR text boxes (median slope of the long lines, ignored above 10 degrees) and groups words whose tilt-corrected centres are within half a line height into one row. The row becomes the `line` of those words. Word IDs, order and boxes do not change, so every cached extraction stays valid. `format_words` and `locate_value` now sort the words of a line left to right.
**Consequence:** A table row reads as one line (`1 Split AC deep cleaning 998719 4unit 900.00 18 3,600.00`), and so does a label with its value (`Grand Total (Rs.) 10,384.00`). That second effect made the model copy the label into the value on a blurred scan; `extract_v4` adds a rule against it. Left and right blocks that share a row of the page (`Bill To` and `Invoice No`) are now one line as well. Cached readings made before this change (`backend/data`, `playground/output/readings`) keep the old line numbers until they are cleared.

## D17. Confidence threshold 0.70 (was 0.80)

**Context:** `D13` says the low-confidence threshold must be tuned on OCR documents. On the six OCR documents of the dev split (11, 19, 20, 27, 29, 30) the required fields with a confidence between 0.71 and 0.80 were all read **correctly** (sample 20 vendor GSTIN 0.77, sample 27 total 0.73), and so a clean scan and a clean receipt went to review. The one wrong value in that group (sample 19 vendor name with a missing space) had confidence 0.98: confidence did not separate right from wrong here.
**Decision:** `AppConfig.confidence_threshold = 0.70`. Chosen on dev only; the test split was not looked at.
**Consequence:** Weak evidence: 30 values on six documents, none of them wrong below 0.9, and 0.70 sits just under the lowest correct value that matters (0.73). A real misread between 0.70 and 0.80 would now pass without a flag. A GSTIN misread is still caught by the checksum, an amount by the sum rules. The test split decides whether this was too low: report any wrong required value with confidence in 0.70-0.80. Fewer documents are "in doubt", so `SECOND_READING=on_doubt` runs less often.

## D18. Deploy on Render's free plan first; scans do not fit in 512 MB

**Context:** The image (SPA + API + RapidOCR) was run with Docker's `--memory=512m` (the free Render limit). The app loaded at 201 MB and a text-layer PDF (sample 01) read at 213 MB, but the first OCR scan (sample 10) was killed for lack of memory (exit 137). Unlimited, the server idles at about 210 MB and OCR brings the peak near 1 GB. Render's free plan also stops the service after 15 minutes without traffic (a cold start of about a minute) and loses the disk on every restart, so SQLite and uploads vanish.
**Decision:** The owner chose to try Render's free plan first (`render.yaml`, Docker, `plan: free`, branch `development`, manual deploys). Alternatives kept open: Render Standard (2 GB, paid) or Hugging Face Spaces (free, more memory, not measured here).
**Consequence:** On the free plan only text-layer PDFs are expected to work; a scan, photo or receipt image is expected to crash the instance, and Render restarts it. The README and the demo script must say so, and the demo video must use text-layer PDFs unless the host changes. If the owner wants scans on the live URL, either move the host or cut OCR memory (smaller image side before OCR, fewer threads) and re-run the evaluation, because that touches the reader. Visitors upload the samples themselves (`samples/generated/`); nothing persists.
