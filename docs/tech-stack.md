# Tech Stack

Same stack as the reference build, except the provider layer: Azure Document Intelligence + Azure OpenAI are replaced by local reading (PyMuPDF, RapidOCR) and free-tier LLMs (Gemini, NVIDIA) through pydantic-ai. Reasons are in [decisions.md](decisions.md).

Constraint: **no paid or card-verified cloud account.**

## Stack

| Area | Reference build | This build |
|---|---|---|
| Language / env | Python 3.12, uv | Same |
| API | FastAPI, uvicorn, python-multipart | Same |
| Models / settings | Pydantic v2, pydantic-settings | Same |
| Database | SQLAlchemy 2, SQLite | Same |
| Document reading | Azure Document Intelligence | **PyMuPDF** (text layer, page images) + **RapidOCR** (onnxruntime) for scans / photos |
| LLM calls | pydantic-ai + openai SDK → Azure OpenAI | **pydantic-ai** → **Gemini** (primary) and **NVIDIA** OpenAI-compatible endpoint (secondary) |
| Tax ID checks | `python-stdnum` (EU VAT) | `python-stdnum` (`in.gstin`) |
| Export | — | `csv` (stdlib), `openpyxl` |
| Sample generation (dev) | reportlab, pillow | Same |
| Backend checks | Ruff | Ruff + **pytest** for pure modules (see D6) |
| Frontend | Vite, React, TypeScript strict, Tailwind CSS v4, pnpm, ESLint | Same |
| HTTP in browser | native `fetch` | Same |
| Container | One Docker image: built SPA + FastAPI | Same |
| Hosting | Azure Container Apps | A free host (Render / Railway / Fly.io / Hugging Face Spaces), decided in M6 |

Exact versions are pinned when the projects are created in M1 (`uv.lock`, `pnpm-lock.yaml`), not written here.

## Dependency policy (copied from the reference build)

- Pin direct dependencies exactly; commit lockfiles.
- Backend `pyproject.toml`: `[tool.uv] add-bounds = "exact"` and `exclude-newer = "7 days"` (no package newer than a week: supply-chain safety).
- Frontend `pnpm-workspace.yaml`: `savePrefix: ""`, `minimumReleaseAge: 10080`, `minimumReleaseAgeStrict: true`.
- Install with `uv sync --locked` and `pnpm install --frozen-lockfile`; run with `uv run --locked --no-sync`.
- Ask the owner before adding any dependency; prefer a small local function.

## Provider interface

pydantic-ai agents live in `backend/app/providers/`. The pipeline calls our own functions, never pydantic-ai directly:

```python
def extract(doc: ReadDocument, settings: Settings) -> ExtractionResult: ...   # classify + fields + evidence IDs
def review_from_images(doc: ReadDocument, doc_type: DocType, settings: Settings) -> SecondReading: ...
def suggest_ledger(fields: ReviewData, catalog: list[Ledger], settings: Settings) -> LedgerSuggestion: ...
def draft_correction_email(fields: ReviewData, issues: list[ValidationIssue], settings: Settings) -> EmailDraft: ...
```

Provider choice is one setting (`LLM_PROVIDER=gemini|nvidia`). Prompts are versioned files in `providers/prompts/`, and the version is stored with every run.

## Open items to confirm in `playground/`

| Item | How we decide |
|---|---|
| Gemini / NVIDIA model names and current free limits | Provider docs on the day → [free-tier-limits.md](free-tier-limits.md) |
| pydantic-ai support for both providers' structured output and image input | `scripts/check_gemini.py`, `scripts/check_nvidia.py` |
| RapidOCR quality on phone photos | Run on degraded samples; compare with docTR if poor |
| Is the second reading worth an extra call? | Evaluation experiment |
| Free host that fits the OCR model and memory | M6 |
