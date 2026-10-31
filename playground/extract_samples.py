"""Experiment: read samples, run reading A (LLM extraction) and score it against manifest.json.

For each document it reports classification, how many fields match the ground truth, and how
many values are really contained in the words the model cited as evidence (a preview of
grounding). Model outputs are cached per prompt (extract_v1 -> output/extract/, others in
output/<prompt>/) so re-runs cost no quota.

Run from backend/:

    uv run --locked --no-sync python ../playground/extract_samples.py 1        # one sample
    uv run --locked --no-sync python ../playground/extract_samples.py all      # all samples
    uv run --locked --no-sync python ../playground/extract_samples.py 1 --show # print the JSON
    ... add --fresh to ignore the cache (uses 1 API call per document)

Prompt experiments (the cache of each prompt version is kept apart, so the extract_v1 outputs
that the other playground scripts read are never overwritten):

    ... all --prompt extract_v2 --split dev        # a model call on a test document is refused
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.providers import EXTRACT_PROMPT, extract  # noqa: E402
from app.reader import read_document  # noqa: E402
from app.schemas.extraction import Evidenced, Extraction  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"


def cache_dir(prompt: str) -> Path:
    """extract_v1 keeps its original folder (the offline playground scripts read it)."""
    return OUTPUT / ("extract" if prompt == "extract_v1" else prompt)


SECONDS_BETWEEN_CALLS = 4.5  # free tier: 15 requests per minute


# ------------------------------------------------ rough normalisation (the real one comes in M2)


def as_amount(text: str | None) -> Decimal | None:
    if text is None:
        return None
    cleaned = re.sub(r"(?i)rs\.?|inr|₹|,|\s", "", text)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def as_date(text: str | None) -> str | None:
    if text is None:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def as_text(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def state_code(text: str | None) -> str | None:
    match = re.search(r"\b(\d{2})\b", text or "")
    return match.group(1) if match else None


def tax_total(extraction: Extraction, head: str) -> Decimal:
    total = Decimal("0")
    for line in extraction.tax_lines:
        if line.head == head:
            total += as_amount(line.amount.value) or Decimal("0")
    return total


AMOUNT_FIELDS = {"taxable_value", "round_off", "total"}


def compare(extraction: Extraction, expected: dict) -> tuple[list[str], list[str]]:
    """Return (correct field names, 'field: got != expected' strings)."""
    right, wrong = [], []

    def check(name: str, ok: bool, got: object) -> None:
        if ok:
            right.append(name)
        else:
            wrong.append(f"{name}: got {got!r}, want {expected[name]!r}")

    for name, want in expected.items():
        if name == "line_items":
            continue
        if name in {"cgst", "sgst", "igst"}:
            got = tax_total(extraction, name.upper())
            check(name, got == Decimal(want), str(got))
            continue
        field: Evidenced = getattr(extraction, name)
        if name in AMOUNT_FIELDS:
            got_amount = as_amount(field.value)
            if name == "round_off" and got_amount is None:
                got_amount = Decimal("0")
            check(name, got_amount == Decimal(want), field.value)
        elif name == "invoice_date":
            check(name, as_date(field.value) == want, field.value)
        elif name == "place_of_supply":
            check(name, state_code(field.value) == want, field.value)
        elif name.endswith("gstin"):
            got = (field.value or "").replace(" ", "").upper() or None
            check(name, got == want, field.value)
        else:
            check(name, as_text(field.value) == as_text(want), field.value)

    want_items = expected["line_items"]
    got_amounts = [as_amount(item.taxable_amount.value) for item in extraction.line_items]
    want_amounts = [Decimal(item["taxable_amount"]) for item in want_items]
    if got_amounts == want_amounts:
        right.append("line_items")
    else:
        wrong.append(f"line_items: got {len(got_amounts)} rows, want {len(want_amounts)}")
    return right, wrong


def evidenced_values(extraction: Extraction) -> list[tuple[str, Evidenced]]:
    pairs: list[tuple[str, Evidenced]] = []
    for name, value in extraction:
        if isinstance(value, Evidenced):
            pairs.append((name, value))
    for i, item in enumerate(extraction.line_items):
        pairs.extend((f"line_items.{i}.{name}", value) for name, value in item)
    for i, line in enumerate(extraction.tax_lines):
        pairs += [(f"tax_lines.{i}.rate", line.rate), (f"tax_lines.{i}.amount", line.amount)]
    return pairs


def grounding(extraction: Extraction, words: dict[str, str]) -> tuple[int, int, list[str]]:
    """Count values whose text really appears in the joined text of the cited words."""
    ok, total, failed = 0, 0, []
    for name, field in evidenced_values(extraction):
        if field.value is None:
            continue
        total += 1
        cited = "".join(words.get(word_id, "") for word_id in field.evidence)
        if field.value.replace(" ", "") in cited.replace(" ", ""):
            ok += 1
        else:
            failed.append(f"{name}={field.value!r} cited {field.evidence}")
    return ok, total, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("which", nargs="*", help="sample numbers, or 'all'")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--prompt", default=EXTRACT_PROMPT, help="file name in providers/prompts")
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--allow-test", action="store_true", help="let a new prompt see test docs")
    options = parser.parse_args()
    fresh, show, prompt = options.fresh, options.show, options.prompt

    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = manifest["documents"]
    if options.which and options.which[0] != "all":
        documents = [documents[int(n) - 1] for n in options.which]
    if options.split:
        documents = [d for d in documents if d["split"] == options.split]
    settings = get_settings()
    cache = cache_dir(prompt)
    cache.mkdir(parents=True, exist_ok=True)
    print(f"prompt {prompt}, cache {cache.name}/, {len(documents)} documents")

    totals = {"right": 0, "fields": 0, "grounded": 0, "values": 0, "type": 0}
    for entry in documents:
        path = APP_CONFIG.samples_dir / entry["file"]
        read = read_document(path.read_bytes()).document
        cache_file = cache / f"{path.stem}.json"
        if cache_file.exists() and not fresh:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            extraction = Extraction.model_validate(cached["extraction"])
            call = cached["call"]
        else:
            if entry["split"] == "test" and not options.allow_test:
                sys.exit(
                    f"{path.name} is in the test split: no new model call on it while prompts "
                    "are being tuned (docs/evaluation.md). Use --split dev, or --allow-test "
                    "for the final evaluation."
                )
            result = extract(read, settings, prompt)
            extraction, call = result.extraction, result.call.__dict__
            cache_file.write_text(
                json.dumps({"extraction": extraction.model_dump(), "call": call}, indent=2),
                encoding="utf-8",
            )
            time.sleep(SECONDS_BETWEEN_CALLS)

        right, wrong = compare(extraction, entry["fields"])
        words = {w.id: w.text for w in read.words}
        grounded, values, ungrounded = grounding(extraction, words)
        type_ok = extraction.document_type == entry["type"]

        totals["right"] += len(right)
        totals["fields"] += len(right) + len(wrong)
        totals["grounded"] += grounded
        totals["values"] += values
        totals["type"] += type_ok

        print(
            f"\n{path.name}: type {extraction.document_type} {'OK' if type_ok else 'WRONG'} | "
            f"fields {len(right)}/{len(right) + len(wrong)} | grounded {grounded}/{values} | "
            f"{call['input_tokens']}+{call['output_tokens']} tokens, {call['seconds']}s"
        )
        for line in wrong:
            print(f"   field   {line}")
        for line in ungrounded:
            print(f"   evidence {line}")
        if show:
            print(json.dumps(extraction.model_dump(), indent=2))

    print(
        f"\nTOTAL  type {totals['type']}/{len(documents)} | "
        f"fields {totals['right']}/{totals['fields']} | "
        f"grounded {totals['grounded']}/{totals['values']}"
    )


if __name__ == "__main__":
    main()
