# Roadmap

Milestones with exit criteria. Each milestone is built as small slices on `development`, and each slice is logged in [build-along.md](build-along.md).

```mermaid
flowchart LR
    M0["M0<br/>Plan<br/>(main)"] --> M1["M1<br/>Read + extract<br/>in playground"]
    M1 --> M2["M2<br/>Ground +<br/>validate"]
    M2 --> M3["M3<br/>Pipeline +<br/>API + DB"]
    M3 --> M4["M4<br/>Review UI"]
    M4 --> M5["M5<br/>Evaluation"]
    M5 --> M6["M6<br/>Ship: security,<br/>deploy, demo"]
    M6 --> M7["M7<br/>Stretch"]
```

| Milestone | Slices | Exit criteria |
|---|---|---|
| **M0 Plan** | Brief, policy, architecture, stack, evaluation, security, decisions, CLAUDE.md | Docs reviewed and committed on `main` |
| **M1 Read + extract** | Backend skeleton + config; reader (PDF text layer + RapidOCR) in `playground/`; Gemini reading A in `playground/`; first 10 synthetic samples | One synthetic invoice → numbered words with boxes → JSON fields with evidence IDs, printed in the console |
| **M2 Ground + validate** | Pydantic models; grounding; normalisation (Indian dates, amounts); validation rules; pytest for these | All rules in policy-rules.md implemented; tests pass offline |
| **M3 Pipeline + API** | Runner, merge, reading B, routing; SQLite models and repository; routes; background task; cache by hash | `curl` upload → document reaches `ready` / `needs_review` with fields, boxes and issues stored |
| **M4 Review UI** | Upload + client picker; document list; review screen with overlay; edit, approve, reject, bulk approve; export | Manual walkthrough of 4 demo documents (clean, bad GSTIN, total mismatch, receipt) works end to end |
| **M5 Evaluation** | Full 36+ corpus with dev/test split; `evaluate_corpus.py`; provider and reading-B experiments; threshold tuning on dev | Results table on the test split committed; safety invariant shows zero violations |
| **M6 Ship** | Security pass; Docker; deploy with sample data; README with results; 3-5 min demo video | Live URL, video, and security checklist all done |
| **M7 Stretch** | Hindi + English, handwritten receipts, GSTR-2B reconciliation, Tally export | Each stretch adds its own samples to the evaluation |

## Demo documents

Four documents carry the demo (like the reference build):

1. Clean intra-state invoice (CGST + SGST) → `ready`
2. Invalid vendor GSTIN → `needs_review`, checksum fix suggested
3. Total mismatch → `needs_review`, cannot be approved
4. Fuel receipt (phone photo) → receipt rules, `ready`
