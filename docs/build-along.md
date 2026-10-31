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
