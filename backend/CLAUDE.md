# Backend guidance

Read the root `CLAUDE.md` first. This file adds backend conventions.

## Stack

Python 3.12, uv, FastAPI + uvicorn, Pydantic v2 + pydantic-settings, SQLAlchemy 2 + SQLite, PyMuPDF, RapidOCR, pydantic-ai (Gemini / NVIDIA), python-stdnum, Ruff, pytest (pure modules only).

## Layout

```text
backend/
├── app/
│   ├── main.py              # FastAPI construction and wiring (create_app factory)
│   ├── config.py            # Settings (env) + fixed app config
│   ├── database.py
│   ├── clients.py           # Fixed client list
│   ├── auth/                # Shared-password gate
│   ├── documents/           # routes, service, repository, models, schemas, projection
│   ├── pipeline/            # PipelineContext + ordered steps
│   ├── reader/              # PDF text layer, OCR, page rendering
│   ├── providers/           # pydantic-ai agents + prompts/; SDK types stop here
│   ├── validation/          # Pure GST rules
│   ├── accounting/          # Ledger catalog
│   ├── correction_email/    # Eligibility + draft schemas
│   └── export/
├── scripts/                 # check_*.py, generate_samples.py, evaluate_corpus.py
├── tests/                   # pytest for validation, grounding, normalisation
├── pyproject.toml
└── uv.lock
```

Do not create empty layers before the build reaches them.

## Code style

- Routes: HTTP parsing, response models, status codes. Service: workflow. Repository: SQLAlchemy only.
- Typed public functions, focused modules. Prefer dataclasses, enums, `pathlib`, `decimal` and the standard library over helper packages.
- Validate at boundaries (files, HTTP input, provider output, DB writes); do not re-validate trusted internal calls.
- Clients are synchronous: use plain `def` handlers, not `async def` around blocking work.

## Configuration

- `app/config.py` is the only configuration boundary. Never call `os.getenv`, read `os.environ` or `load_dotenv` elsewhere, including scripts.
- Fixed policy (tolerances, size limits, catalog) is code config, not environment variables.
- Fail clearly when a required key is missing; no silent fallbacks.

## Dependencies

Keep `[tool.uv] add-bounds = "exact"` and `exclude-newer = "7 days"`. Install with `uv sync --locked`; run with `uv run --locked --no-sync ...`. Ask before adding anything.

## Verification

```bash
uv run --locked --no-sync ruff check app scripts tests
uv run --locked --no-sync pytest
```

Provider checks and corpus evaluation use free-tier quota: state the number of calls before running. If the SQLite schema changes during development, delete `backend/data/*.db` so it is recreated.
