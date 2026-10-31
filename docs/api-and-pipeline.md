# API endpoints and pipeline

Target HTTP API for the backend. Implemented in milestone M3; keep this file in sync with the code.

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
| `issues` | array | `{ code, severity, field, message, supplier_fixable }` |
| `ledger` | object \| null | `{ suggested_code, reason, selected_code, overridden }` |
| `supplier_action_required` | bool | True when supplier-fixable issues exist |
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
