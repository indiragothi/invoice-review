# Free-Tier Limits

The reference build has a `pricing.md` for Azure costs. This project pays nothing, so the constraint is **quota**, not money. This page records what one document costs in API calls and how many documents fit in a day.

## Calls per document

| Action | LLM calls | Sends |
|---|---|---|
| Upload (normal) | 2 | Extraction: numbered words (+ page image if needed). Ledger: normalised fields + catalog |
| Upload with second reading | 3 | + page images for the vision reading |
| Correction-email draft | 1 | Normalised fields + eligible issues, never the file |
| Re-upload of the same file | 0 for reading | Cached by SHA-256 |
| Retry of a failed document | 2-3 | |
| Corpus evaluation (36 docs) | ~72-108 | Cached between runs unless prompts change |

PDF text extraction, OCR, validation and storage are local and free.

## Provider limits

Free-tier limits change often. **Check the provider pages on the day you start and fill this table in with the date.** Model names and limits go in `backend/.env`, never in code.

| Provider | Model | Requests / minute | Requests / day | Tokens / minute | Checked on |
|---|---|---|---|---|---|
| Gemini (AI Studio free tier) | **`gemini-3.5-flash-lite`** (chosen) | 15 | 500 | 250K | 2026-10-31 |
| Gemini (AI Studio free tier) | `gemini-3.8-flash` | 5 | 20 | 250K | 2026-10-31 |
| NVIDIA (build.nvidia.com) | | | | | |

Source: the owner's AI Studio rate-limit page (limits are per project; daily quota resets at midnight Pacific time). Model list and free-tier availability checked on Google's models and pricing pages the same day. `gemini-4-argon` has no free tier; `gemini-2.5-*` is closed to new users.

## Capacity

```
documents per day ≈ requests per day ÷ calls per document
```

| Model | Calls / document | Documents / day | One 36-document evaluation |
|---|---|---|---|
| `gemini-3.5-flash-lite` | 2-3 | ~165-250 | fits easily (~72-108 calls) |
| `gemini-3.8-flash` | 2-3 | ~6-10 | does not fit in one day |

**Decision:** `gemini-3.5-flash-lite` is the default model. `gemini-3.8-flash` may be tried later for the second reading only, if the evaluation shows Flash-Lite is too weak. At 15 requests per minute, a burst of uploads needs the retry-with-backoff path.

## Behaviour at the limit

- `429` from a provider → retry with exponential backoff (a few attempts).
- Still failing → the document is saved as `failed` with "provider busy, retry later"; the UI shows a Retry button.
- The evaluation script stops cleanly and resumes from its cache.

## Privacy reminder

Free tiers may use prompts for training. Only fictional, synthetic or fully redacted documents.
