# Decision Log

Short records of decisions that shape the project. Add a new entry instead of rewriting an old one; mark the old one *Superseded*.

## D1. No Azure; free tools only

**Context:** Dave Ebbelaar's reference build uses Azure Document Intelligence + Azure OpenAI. Azure sign-up needs card verification, which is not available.
**Decision:** Local PDF text / OCR + free-tier LLM APIs (Gemini primary, NVIDIA secondary).
**Consequence:** We must build our own per-field confidence and provenance, which Azure gave for free. See D3.

## D2. Target user: Indian CA firm

**Context:** A generic "invoice extractor" competes with many demos. Indian GST bills have concrete, checkable rules.
**Decision:** Build for an accounts executive at a small CA firm doing GST work.
**Consequence:** GSTIN checksum, tax split, buyer = client, Indian dates and number formats are first-class. A light `CLIENT` table is needed.

## D3. OCR + LLM with evidence pointers, not LLM-only

**Context:** A vision LLM alone gives no reliable bounding boxes and no real confidence.
**Decision:** Read words with positions (PDF text layer or OCR); the LLM returns values plus the IDs of the words that support them; code verifies the value is in those words and builds the box.
**Consequence:** Real provenance, hallucination check, and a confidence signal from OCR. Costs a grounding step and careful normalisation (e.g. "1,23,456.00" spans several OCR words).

## D4. One combined classify + extract call; second reading only on doubt

**Context:** Free-tier rate limits.
**Decision:** Reading A does classification and extraction in one call. Reading B (vision) runs when a required field is ungrounded or low-confidence, or when `SECOND_READING=always`.
**Consequence:** ~1-2 calls per document. The evaluation must show what B adds.

## D5. React + FastAPI, like the reference build

**Context:** Streamlit is faster to build but weak at an interactive page overlay.
**Decision:** Vite + React + TypeScript + Tailwind frontend, FastAPI backend.
**Consequence:** More code, but a review screen that looks like a real product.

## D6. Pure modules get unit tests

**Context:** The reference build avoids test suites. Here the validation rules (GSTIN, tax maths, dates) are money logic, and the roadmap asks for real test results.
**Decision:** pytest for `validation/`, `pipeline/ground.py` and `pipeline/normalise.py` only. Providers and UI are verified by the live evaluator and a manual walkthrough.
**Consequence:** Fast, offline tests where bugs are most costly; no mocking of LLMs.

## D7. Background task, no queue

**Context:** Extraction takes several seconds per document.
**Decision:** `POST /documents` returns `202` and runs the pipeline in a FastAPI background task; the UI polls.
**Consequence:** Fine for one user. Not durable across restarts; a stuck `processing` document can be retried.

## D8. Date-aware GST slabs in config

**Context:** GST rate slabs changed from 22 September 2025.
**Decision:** Keep slabs in a dated table; an off-slab rate is only a warning.
**Consequence:** Old and new bills are both handled; the table must be checked against official notifications.
