# API endpoints and pipeline

Target HTTP API for the backend. Implemented in milestone M3; keep this file in sync with the code.

**Built so far:** `/health`, `GET /api/clients`, `GET /api/accounting/ledgers`, `POST` / `GET /api/documents`, `GET /api/documents/{id}`, `/file`, `/pages/{n}`, `PUT /api/documents/{id}` (field edit), `PUT .../ledger`, `POST .../decision`, `POST /bulk-approve`, `POST .../correction-email`, `POST .../retry`, `DELETE`, `GET /api/export`. Not built yet: auth.

Base URL (local): `http://localhost:8000` · Swagger UI: `/docs` · CORS allows the Vite app at `http://localhost:5173` (or `ALLOWED_ORIGIN`).

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/auth/session` | Is the password gate on, and is this browser signed in |
| `POST` | `/api/auth/login` | `{ "password": "..." }` → session cookie (only when the gate is on) |
| `POST` | `/api/auth/logout` | Clear the cookie |
| `GET` | `/api/clients` | Fixed client list (id, name, GSTIN, state) |
| `GET` | `/api/accounting/ledgers` | Fixed ledger catalog |
| `POST` | `/api/documents` | Upload (`file`, `client_id`) and run the full pipeline |
| `GET` | `/api/documents` | List reviews, newest first; filters `status`, `client_id` |
| `GET` | `/api/documents/{id}` | One review |
| `GET` | `/api/documents/{id}/file` | Original upload bytes |
| `GET` | `/api/documents/{id}/pages/{n}` | Rendered page image (PNG) for the highlight overlay |
| `PUT` | `/api/documents/{id}` | Field corrections → source `human`, re-validate |
| `PUT` | `/api/documents/{id}/ledger` | `{ "ledger_code": "6130" }`, must exist in the catalog |
| `POST` | `/api/documents/{id}/decision` | `{ "decision": "approved" \| "rejected" }` |
| `POST` | `/api/documents/bulk-approve` | `{ "ids": [...] }`; only `ready` documents with a selected ledger are approved, the rest are returned as skipped |
| `POST` | `/api/documents/{id}/retry` | Re-run the pipeline for a `failed` document |
| `POST` | `/api/documents/{id}/correction-email` | Draft a supplier correction email (never sent) |
| `GET` | `/api/export` | `?format=csv\|xlsx&client_id=` approved records only |
| `DELETE` | `/api/documents/{id}` | Delete a review and its files (demo reset) |

## Status codes

| Code | When |
|---|---|
| `201` | Upload processed (any status, including `needs_review`) |
| `401` | Password gate on and no valid session |
| `404` | Unknown document / client / ledger |
| `409` | Approve with open blocking errors or no ledger; edit a decided record; draft an email with no eligible issues |
| `413` | File over 5 MB or more than 5 pages |
| `415` | Not a PDF / JPEG / PNG (checked by magic bytes) |
| `422` | Bad request body, or the document is neither an invoice nor a receipt |
| `502` | Provider failed after retries; the record is saved as `failed` |

A document that fails after it was saved (upload or retry) answers `502` (provider) or `422` (not an invoice or receipt, or no readable text) with a body `{ "detail": "...", "document": <DocumentResponse> }`; the record stays in the list as `failed` and can be retried (`failed` documents have `issues: []`).

## Editing fields

`PUT /api/documents/{id}` with `{ "fields": { "<path>": "<text>" | null } }` (1 to 200 entries). A path is one of the keys of `review_data.fields`: `vendor_gstin`, `invoice_date`, `total`, `line_items[2].taxable_amount`, `tax_lines[0].amount`, ... The value is the corrected text exactly as the reviewer types it (`"1,18,000.00"`, `"14-08-2026"`); `null` or empty clears the field. The server normalises it like any extracted value.

An edited field gets `source: "human"`, `confidence: 1.0` and `grounding: "grounded"` (`"missing"` when cleared); `original` keeps the model's reading, and the history gets an `edited` entry with `{path: {from, to}}`. Then every rule runs again, including the duplicate checks, and the status follows the result: `needs_review` -> `ready` when the last blocking error is fixed, `ready` -> `needs_review` when an edit breaks a rule. A format cap still applies to a human value that fails its own format (an invalid GSTIN is capped at 0.3 and keeps its blocking error).

`404` unknown document; `422` unknown path (nothing is applied), a value over 500 characters or an empty `fields`; `409` for a decided (`approved` / `rejected`), `failed` or `processing` document. Adding or removing line-item rows is not supported yet.

## Export

`GET /api/export?format=csv|xlsx&client_id=C001` returns the **approved** documents, oldest first, as an attachment (`approved-YYYY-MM-DD.csv` / `.xlsx`). `format` defaults to `csv`; `client_id` is optional. With nothing approved the file has only the headings. Unknown client -> `404`; unknown format -> `422`.

Columns: document id, client id / name / GSTIN, type, vendor or merchant, vendor GSTIN, number, date, place of supply (state code), taxable value, CGST, SGST, UTGST, IGST, cess, round off, total, ledger code and name, whether the reviewer changed the ledger, open warnings (codes), approval time, original file name. Values are the current normalised ones, so the reviewer's corrections are in. CSV is UTF-8 with a BOM (Excel shows names correctly), amounts with two decimals, dates `DD-MM-YYYY`. XLSX has real numbers and real dates, so sums and filters work.

Text that comes from the bill or the upload is made safe for spreadsheets: a value starting with `=`, `+`, `-`, `@`, tab or carriage return gets a leading `'`, and in XLSX such cells are stored as text. Amounts are numbers and are not touched.

## Correction email

`POST /api/documents/{id}/correction-email` (no body) -> `200 { "subject", "body", "issue_codes" }`. The app only **drafts** text; the reviewer copies it into their own email client, and there is no code that sends mail. The issues come from the fixed supplier-fixable list (`policy-rules.md`), never from the model; the draft is written from the current normalised fields (including the reviewer's edits), not from the file. One LLM call per draft.

`404` unknown document; `409` when the document is `processing` / `failed` or has no supplier-fixable issue; `502` when the provider fails after the retries. The draft is not stored; the history gets a `correction_email_drafted` entry with the issue codes.

## Decisions

- `PUT /api/documents/{id}/ledger` `{ "ledger_code": "6130" }` sets `ledger.selected_code` (the reviewer confirms the suggestion or overrides it; `overridden` is true when it differs). Unknown code -> `404`; decided or not yet processed document -> `409`. The suggestion is never selected automatically.
- `POST /api/documents/{id}/decision` `{ "decision": "approved" | "rejected" }`. **Approve** needs status `ready`, no blocking error and a valid selected ledger, otherwise `409` with the reasons in `detail`. **Reject** is allowed from `ready` or `needs_review`. A decided record is locked: every further decision or ledger change is `409`.
- `POST /api/documents/bulk-approve` `{ "ids": [...] }` (at most 200) -> `200 { "approved": [DocumentResponse], "skipped": [{ "id", "reason" }] }`. Same check per document; unknown ids are skipped with "Document not found."

## DocumentResponse

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID string | Stable review id |
| `client_id` | string | Client the bill belongs to |
| `original_filename`, `content_type`, `page_count` | | Upload facts |
| `status` | string | `processing`, `ready`, `needs_review`, `approved`, `rejected`, `failed` |
| `classification` | object \| null | `invoice` / `receipt` + reason |
| `review_data` | object \| null | Flat editable fields; each with value, source, confidence, agreement, evidence box (see [architecture.md](architecture.md#7-persistence)) |
| `document_review` | object \| null | Second-reading comparison per field |
| `issues` | array | `{ code, severity, field, message, suggestion }`; `supplier_fixable` is true when the supplier can fix it (fixed list) |
| `ledger` | object \| null | `{ suggested_code, reason, selected_code, overridden }` |
| `document_type` | string \| null | `invoice` or `receipt` |
| `supplier_action_required` | bool | True when at least one issue is supplier-fixable |
| `history` | array | Edits and decisions |
| `pipeline_run` | object \| null | Provider, model, prompt version, API calls, milliseconds |
| `error_message` | string \| null | Set when `failed` |
| `created_at`, `updated_at` | ISO datetime | |

## Pipeline steps

`build_default_pipeline()` runs, in order:

1. **Reading:** PDF text layer (PyMuPDF) or OCR (RapidOCR) → numbered words with boxes and confidence.
2. **Extraction:** one LLM call classifies the document and extracts fields with evidence word IDs.
3. **Grounding:** code checks every value against its cited words and builds the box.
4. **Document review:** independent vision reading when needed; merge fills only missing fields; agree / differ / missing per field.
5. **Validation:** normalise, then pure invoice / receipt rules, duplicates, status.
6. **Ledger suggestion:** one LLM call over normalised fields + catalog; code checks the code exists.

LLM calls per upload: **2 normally, 3 when the second reading runs**, plus 1 per correction-email draft. See [free-tier-limits.md](free-tier-limits.md).
