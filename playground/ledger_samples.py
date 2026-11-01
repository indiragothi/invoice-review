"""Experiment: ledger suggestion (LLM call 3) on the samples, scored against `expected_ledger`.

The input is the normalised document built from the cached reading-A extraction, so the only new
model call per document is the ledger one. Results are cached per prompt in output/<prompt>/
(re-runs cost no quota). A model call on a test-split document is refused unless --allow-test
(docs/evaluation.md). Run from backend/:

    uv run --locked --no-sync python ../playground/ledger_samples.py --split dev   # 7 calls once
    uv run --locked --no-sync python ../playground/ledger_samples.py --split dev --fresh
"""

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.accounting.catalog import LEDGERS_BY_CODE, checked_ledger_code  # noqa: E402
from app.clients import CLIENTS_BY_ID  # noqa: E402
from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.normalisation.assemble import normalise_extraction  # noqa: E402
from app.providers import LEDGER_PROMPT, CallInfo, LedgerResult, suggest_ledger  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.ledger import LedgerChoice  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"
EXTRACT_CACHE = OUTPUT / "extract"
SECONDS_BETWEEN_CALLS = 4.5  # free tier: 15 requests per minute


def cached_ledger(stem: str, prompt: str = LEDGER_PROMPT) -> LedgerResult | None:
    path = OUTPUT / prompt / f"{stem}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return LedgerResult(choice=LedgerChoice(**data["choice"]), call=CallInfo(**data["call"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--prompt", default=LEDGER_PROMPT)
    options = parser.parse_args()

    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = [
        d for d in manifest["documents"] if not options.split or d["split"] == options.split
    ]
    settings = get_settings()
    (OUTPUT / options.prompt).mkdir(parents=True, exist_ok=True)
    print(f"prompt {options.prompt}, {len(documents)} documents")

    right = 0
    for entry in documents:
        stem = Path(entry["file"]).stem
        result = None if options.fresh else cached_ledger(stem, options.prompt)
        if result is None:
            if entry["split"] == "test" and not options.allow_test:
                sys.exit(f"{stem} is in the test split: no new model call (docs/evaluation.md).")
            cached = json.loads((EXTRACT_CACHE / f"{stem}.json").read_text(encoding="utf-8"))
            document = normalise_extraction(Extraction.model_validate(cached["extraction"]))
            assert document is not None
            client = CLIENTS_BY_ID[entry["client"]]
            result = suggest_ledger(document, client.name, settings, options.prompt)
            path = OUTPUT / options.prompt / f"{stem}.json"
            path.write_text(
                json.dumps({"choice": result.choice.model_dump(), "call": result.call.__dict__}),
                encoding="utf-8",
            )
            time.sleep(SECONDS_BETWEEN_CALLS)

        code = checked_ledger_code(result.choice.code)
        ok = code == entry["expected_ledger"]
        right += ok
        name = LEDGERS_BY_CODE[code].name if code else "NOT IN CATALOG"
        print(
            f"{'OK ' if ok else 'BAD'} {stem}: {result.choice.code} {name} "
            f"(want {entry['expected_ledger']}) | {result.call.input_tokens}+"
            f"{result.call.output_tokens} tokens, {result.call.seconds}s"
        )
        print(f"      {result.choice.reason}")
    print(f"\nLEDGER {right}/{len(documents)} match expected_ledger")


if __name__ == "__main__":
    main()
