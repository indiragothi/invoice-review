# Tech Stack

Constraint: **no paid or card-verified cloud account.** Everything runs locally or on free-tier APIs. The reasons behind each choice are in [decisions.md](decisions.md).

## Stack

| Area | Choice | Role |
|---|---|---|
| Language / env | Python 3.12, `uv` | Reproducible, locked installs |
| API | FastAPI + Pydantic v2 | Typed routes; Pydantic models double as LLM output schemas |
| Database | SQLite via SQLAlchemy 2 | Zero setup |
| PDF handling | PyMuPDF | Page rendering and native text layer with word boxes |
| OCR | RapidOCR (onnxruntime) | Word boxes + confidence for scans / photos; local, light on Windows |
| Primary LLM | Gemini via `google-genai` | Classify + extract with structured JSON; vision for reading B |
| Secondary LLM | NVIDIA hosted models via `openai` SDK (OpenAI-compatible endpoint) | Second opinion and fallback |
| GSTIN | `python-stdnum` (`in.gstin`) | Offline format + checksum |
| Retries | small local helper (exponential backoff) | Free-tier rate limits |
| Export | `csv` (stdlib), `openpyxl` | CSV / Excel |
| Frontend | Vite, React, TypeScript (strict), Tailwind CSS, pnpm | Page viewer with highlight overlay |
| PDF in browser | Page images rendered by the backend | Avoids a PDF.js dependency; boxes map 1:1 to image pixels |
| Backend checks | Ruff, pytest (pure modules only) | |
| Frontend checks | `tsc`, ESLint, `vite build` | |
| Container / deploy | Docker; a free-tier host (Render / Railway / Fly.io / Hugging Face Spaces) | Decided in milestone M6 |

## Open items to confirm in `playground/` before building on them

| Item | How we decide |
|---|---|
| Exact Gemini / NVIDIA model names and current free limits | Check provider docs on the day; keep names in `.env`, never hard-code |
| RapidOCR quality on phone photos | Run on 5 degraded samples; compare with docTR if poor |
| Is reading B worth an extra call? | Evaluation experiment "A only vs A+B" |
| Free host for deployment | Must fit OCR model size and memory |

## Provider interface

```python
class LLMProvider(Protocol):
    name: str

    def read_text(self, doc: ReadDocument, prompt: PromptVersion) -> ReadingA:
        """Classify + extract from numbered words. Returns values with evidence word IDs."""

    def read_image(self, doc: ReadDocument, doc_type: DocType, prompt: PromptVersion) -> ReadingB:
        """Independent extraction from page images."""
```

Switching provider is one setting (`LLM_PROVIDER=gemini|nvidia`). Prompts live in `providers/prompts/` as versioned files (`read_text_v1.md`), and the version is stored with every run so evaluation results stay comparable.

## Free-tier cautions

- Limits change and are low. Retry with backoff, then mark the document `failed` with a clear "provider busy, retry" message.
- Cache readings by file hash so re-runs and evaluation do not burn quota.
- Free tiers may use prompts for training. Only fictional, synthetic or redacted documents are sent.
- Keys live in `backend/.env`, never in git.

## Dependency policy

Pin direct dependencies exactly and commit lockfiles. Prefer a small local function over a new package. Ask the owner before adding a dependency.
