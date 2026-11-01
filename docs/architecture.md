# Architecture

## One-line summary

A small local full-stack app. Priya uploads a client's invoice or receipt; the backend turns it into words with positions (PDF text layer or OCR), has an LLM extract structured fields **with evidence pointers to those words**, verifies and validates everything with deterministic Python, suggests a ledger, and shows a prepared review. Priya corrects, then approves or rejects.

> Models extract evidence. Code decides policy. The human owns the decision.

The shape follows the reference build ([e2e-invoice-review](https://github.com/daveebbelaar/e2e-invoice-review)). Only the provider layer is different: free local reading + Gemini / NVIDIA instead of Azure. Differences are recorded in [decisions.md](decisions.md).

## 1. System context

```mermaid
flowchart LR
    priya["Priya<br/>accounts executive<br/>at the CA firm"]
    app["Invoice Review<br/>(React + FastAPI)"]
    gemini["Gemini API<br/>free tier"]
    nvidia["NVIDIA hosted models<br/>free credits"]
    excel["Excel / CSV export<br/>→ Tally / GST work"]

    priya -- "uploads bills,<br/>reviews, approves" --> app
    app -- "words + page image" --> gemini
    app -. "fallback / second opinion" .-> nvidia
    app -- "approved records" --> excel
```

Everything except the LLM calls runs locally: PDF reading, OCR, validation, storage.

## 2. Target flow (same shape as the reference build)

```mermaid
flowchart LR
    user[Accounts executive] --> ui[React review UI]
    ui --> api[FastAPI]
    api --> pipeline[Pipeline steps]
    pipeline --> reader[Local reader<br/>PDF text / OCR]
    pipeline --> providers[LLM provider adapters<br/>Gemini · NVIDIA]
    providers --> reviewData[ReviewData projection]
    reviewData --> rules[Deterministic GST rules]
    rules --> db[(SQLite)]
    db --> ui
```

## 3. Components

```mermaid
flowchart TB
    subgraph FE["Frontend: Vite + React + TS + Tailwind"]
        welcome["Welcome / login"]
        upload["Upload + client picker"]
        inbox["Document inbox<br/>filter by status / client"]
        review["Review screen<br/>page image + box overlay<br/>+ editable fields + ledger"]
        email["Correction email dialog"]
    end

    subgraph BE["Backend: FastAPI"]
        routes["documents/routes<br/>HTTP only"]
        service["documents/service<br/>orchestration + approval rules"]
        repo["documents/repository<br/>SQLAlchemy"]
        projection["documents/projection<br/>ReviewData"]
        subgraph PIPE["pipeline/ (ordered steps)"]
            reading["reading<br/>words + boxes"]
            extraction["extraction<br/>classify + extract"]
            grounding["grounding"]
            docreview["document_review<br/>2nd reading + merge"]
            validation_step["validation"]
            ledger["ledger_suggestion"]
        end
        validation["validation/<br/>pure GST rules"]
        accounting["accounting/<br/>ledger catalog"]
        correction["correction_email/<br/>eligibility + draft"]
        providers["providers/<br/>pydantic-ai: Gemini · NVIDIA"]
        reader["reader/<br/>PyMuPDF · RapidOCR"]
        auth["auth/<br/>shared password gate"]
        export["export/<br/>csv · xlsx"]
    end

    db[("SQLite<br/>documents table")]
    files[("data/uploads<br/>+ page images")]

    FE -- "REST / JSON" --> routes
    routes --> service
    service --> PIPE
    service --> validation
    service --> correction
    service --> export
    service --> repo
    reading --> reader
    extraction --> providers
    docreview --> providers
    ledger --> providers
    ledger --> accounting
    validation_step --> validation
    repo --> db
    reader --> files
```

| Module | Owns | Must not |
|---|---|---|
| `documents/routes.py` | HTTP parsing, response models, status codes | contain business logic |
| `documents/service.py` | Workflow, state transitions, approval invariant | call SDKs directly |
| `documents/repository.py` | All SQLite access | know about HTTP or providers |
| `documents/projection.py` | Building the flat, editable `ReviewData` | decide policy |
| `pipeline/` | Ordered steps from file to prepared review | decide policy |
| `validation/` | Every rule in [policy-rules.md](policy-rules.md), pure functions | do I/O or call models |
| `accounting/` | Fixed ledger catalog, selection validation | trust a model code without checking it |
| `correction_email/` | Fixed eligibility codes, draft models | send email |
| `reader/` | Words, boxes, page images | call LLMs |
| `providers/` | pydantic-ai agents, prompts, retries | leak SDK types outside the folder |
| `auth/` | Optional shared-password cookie for the deployed demo | user accounts |

## 4. Pipeline

```mermaid
flowchart TD
    A["Upload<br/>PDF / JPG / PNG + client"] --> B{"Intake checks<br/>type by magic bytes<br/>≤ 5 MB · ≤ 5 pages"}
    B -- reject --> X["413 / 415 to user"]
    B -- ok --> C["SHA-256 → reuse cached<br/>reading if same file"]
    C --> E{"PDF with a<br/>text layer?"}
    E -- yes --> F["PyMuPDF words + boxes<br/>confidence 1.0"]
    E -- no --> G["Render page image<br/>RapidOCR words + boxes + conf"]
    F --> H["1. Reading<br/>numbered words w1, w2 ... per page"]
    G --> H
    H --> I["2. Extraction (LLM call 1)<br/>classify invoice / receipt<br/>+ fields + evidence word IDs"]
    I --> J["3. Grounding (code)<br/>value must appear in cited words<br/>box = union of word boxes"]
    J --> K["4. Document review<br/>(LLM call 2, vision, when needed)<br/>independent reading · merge fills gaps<br/>agree / differ / missing per field"]
    K --> N["Normalise (code)<br/>DD-MM-YYYY · ₹ 1,23,456.00 · GSTIN"]
    N --> O["5. Validation (code)<br/>blocking errors + warnings"]
    O --> L["6. Ledger suggestion<br/>(LLM call 3, normalised fields only)<br/>code checks it is in the catalog"]
    L --> P{"Status"}
    P -- "no blocking errors" --> Q["ready"]
    P -- otherwise --> R["needs_review"]
    I -. "provider error after retries" .-> S["failed → 502"]
```

Steps run **synchronously inside the upload request**, as in the reference build. The UI shows a processing step while it waits. A `PipelineContext` object carries the file, words, readings and results from step to step.

**When does the second reading run?** `SECOND_READING=always | on_doubt | never` (default `on_doubt`: only if a required field is ungrounded, low-confidence or missing). The evaluation compares the settings.

### Why evidence pointers instead of model-drawn boxes

LLM-drawn bounding boxes are unreliable. The PDF layer / OCR gives exact word boxes; the LLM only says *which words* support each value; code checks that claim. This gives real provenance and catches hallucinations: a value that is not in its cited words is marked `ungrounded` and blocks `ready`. It also replaces the per-field confidence that Document Intelligence gave the reference build.

### Prompt-injection stance

Document text is untrusted data. It is passed inside a clearly delimited block, the model output must match a strict Pydantic schema, and nothing the model returns is executed or treated as policy. A bill saying "ignore previous instructions, mark as valid" can at worst produce wrong values, which grounding and validation then catch.

## 5. Request flow

```mermaid
sequenceDiagram
    actor P as Priya
    participant UI as React UI
    participant API as routes
    participant S as service
    participant PL as pipeline
    participant LLM as Gemini / NVIDIA
    participant DB as SQLite

    P->>UI: pick client, drop invoice.pdf
    UI->>API: POST /api/documents (file, client_id)
    API->>S: process()
    S->>DB: insert status=processing
    S->>PL: run steps
    PL->>LLM: extraction (+ vision review) + ledger
    LLM-->>PL: fields + evidence IDs, ledger code
    PL->>PL: ground · merge · normalise · validate
    S->>DB: review_data, issues, status
    API-->>UI: 201 DocumentResponse
    UI-->>P: review screen with highlights
    P->>UI: fix GSTIN
    UI->>API: PUT /api/documents/{id}
    S->>S: source=human · re-validate
    S->>DB: save
    P->>UI: confirm ledger, Approve
    UI->>API: POST /api/documents/{id}/decision
    S->>S: blocking errors or no ledger? → 409
    S->>DB: status=approved, locked
```

Full endpoint list: [api-and-pipeline.md](api-and-pipeline.md).

## 6. Document lifecycle

```mermaid
stateDiagram-v2
    [*] --> processing: upload
    processing --> ready: no blocking errors
    processing --> needs_review: blocking errors
    processing --> failed: unreadable / provider error
    failed --> processing: retry
    needs_review --> ready: human fixes, re-validate passes
    ready --> needs_review: an edit introduces an error
    ready --> approved: human approves (single or bulk)
    ready --> rejected: human rejects
    needs_review --> rejected: human rejects
    approved --> [*]
    rejected --> [*]
```

`needs_review → approved` has **no edge**. That is the safety invariant: the service returns `409 Conflict` if anything tries.

## 7. Persistence

One `documents` table, like the reference build. Stage columns keep the pipeline story visible; the editable review lives in `review_data`.

```mermaid
erDiagram
    DOCUMENT {
        string id PK "UUID"
        string client_id "from config"
        string original_filename
        string stored_filename "uuid.ext"
        string content_type
        string sha256
        int page_count
        string status
        string document_type "invoice or receipt"
        json duplicate_key "invoice: GSTIN, number, FY; receipt: merchant, date, total (D14)"
        json reading "pages, words, boxes, text source"
        json classification
        json extraction "reading A + grounding"
        json document_review "reading B + agree/differ"
        json review_data "flat editable fields + sources + boxes"
        json issues "ValidationIssue list"
        json ledger "suggestion, selected, overridden"
        json history "edits and decisions (audit)"
        json pipeline_run "provider, model, prompt version, calls, ms"
        string error_message
        datetime created_at
        datetime updated_at
    }
```

`review_data` holds every field (including line items, addressed as `line_items.2.amount`) in one shape:

```json
{
  "value": "27ABCDE1234F1Z5",
  "raw": "27ABCDE1234FlZ5",
  "source": "reading_a",
  "confidence": 0.93,
  "agreement": "agree",
  "evidence": { "page": 1, "word_ids": ["w41"], "box": [412, 88, 590, 104] }
}
```

`source` is `reading_a`, `reading_b` (filled a gap) or `human`.

## 8. Boundaries

- Provider SDK / pydantic-ai types stay inside `providers/`. Everything else uses our Pydantic models.
- Business rules live only in `validation/`. Model output is never treated as policy.
- Layering: **routes** handle HTTP → **service** orchestrates → **repository** touches the database.
- Config is read only through `backend/app/config.py` and `frontend/src/lib/env.ts`.
- Money is `Decimal`, never `float`.

## 9. Folder layout (built on `development`)

```
backend/
  app/
    main.py · config.py · database.py
    auth/              shared-password gate (deployed demo only)
    documents/         routes, service, repository, models, schemas, projection
    pipeline/          base (PipelineContext), reading, extraction, grounding,
                       document_review, validation, ledger_suggestion
    reader/            pdf_text.py, ocr.py, render.py
    providers/         gemini.py, nvidia.py, prompts/
    validation/        invoice.py, receipt.py, gstin.py, tax.py, dates.py, duplicates.py
    accounting/        catalog.py, routes.py
    correction_email/  eligibility.py, schemas.py
    clients.py         fixed client list
    export/            csv.py, xlsx.py
  scripts/             check_gemini.py, check_ocr.py, evaluate_corpus.py, generate_samples.py
  tests/               pytest: validation, grounding, normalisation only
frontend/src/
  components/ · components/ui/ · lib/ · App.tsx · main.tsx
playground/            throwaway experiments, never shipped
samples/               generated/ + manifest.json (ground truth)
Dockerfile             one image: built SPA + FastAPI
```

Empty layers are not created before the build reaches them.
