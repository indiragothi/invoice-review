"""Experiment: the second, independent reading (reading B) from page images, vs reading A.

For each document: reading B (one vision call, cached in output/<prompt>/), then the comparison
with the cached reading A: agree / differ / missing / filled per field, and how many manifest
fields each reading got right. A new call on a test-split document is refused unless
--allow-test. Run from backend/:

    uv run --locked --no-sync python ../playground/second_reading_samples.py 1        # sample 1
    uv run --locked --no-sync python ../playground/second_reading_samples.py --split dev
    ... --fresh ignores the cache (1 call per document)
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_samples import compare  # noqa: E402

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.pipeline.agreement import compare_and_fill  # noqa: E402
from app.providers import (  # noqa: E402
    REVIEW_PROMPT,
    CallInfo,
    SecondReadingResult,
    review_from_images,
)
from app.reader import read_document  # noqa: E402
from app.schemas.extraction import (  # noqa: E402
    Evidenced,
    ExtractedLineItem,
    ExtractedTaxLine,
    Extraction,
)
from app.schemas.second_reading import SecondReading  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"
SECONDS_BETWEEN_CALLS = 4.5  # free tier: 15 requests per minute


def cached_second(stem: str, prompt: str) -> SecondReadingResult | None:
    path = OUTPUT / prompt / f"{stem}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SecondReadingResult(
        reading=SecondReading.model_validate(data["reading"]), call=CallInfo(**data["call"])
    )


def as_extraction(document_type: str, b: SecondReading) -> Extraction:
    """Reading B in the shape the playground scorer knows (no evidence)."""

    def e(value: str | None) -> Evidenced:
        return Evidenced(value=value, evidence=[])

    return Extraction(
        document_type=document_type,  # type: ignore[arg-type]
        classification_reason="",
        vendor_name=e(b.vendor_name),
        vendor_gstin=e(b.vendor_gstin),
        buyer_name=e(b.buyer_name),
        buyer_gstin=e(b.buyer_gstin),
        invoice_number=e(b.invoice_number),
        invoice_date=e(b.invoice_date),
        place_of_supply=e(b.place_of_supply),
        line_items=[
            ExtractedLineItem(
                description=e(i.description),
                hsn_sac=e(i.hsn_sac),
                quantity=e(i.quantity),
                rate=e(i.rate),
                gst_rate=e(i.gst_rate),
                taxable_amount=e(i.taxable_amount),
            )
            for i in b.line_items
        ],
        taxable_value=e(b.taxable_value),
        tax_lines=[
            ExtractedTaxLine(head=t.head, rate=e(t.rate), amount=e(t.amount)) for t in b.tax_lines
        ],
        round_off=e(b.round_off),
        total=e(b.total),
        amount_in_words=e(b.amount_in_words),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("which", nargs="*", help="sample numbers (1-12)")
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--prompt", default=REVIEW_PROMPT)
    options = parser.parse_args()

    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["documents"]
    if options.which:
        entries = [entries[int(n) - 1] for n in options.which]
    if options.split:
        entries = [d for d in entries if d["split"] == options.split]
    settings = get_settings()
    (OUTPUT / options.prompt).mkdir(parents=True, exist_ok=True)

    totals = Counter()
    for entry in entries:
        path = APP_CONFIG.samples_dir / entry["file"]
        stem = path.stem
        read = read_document(path.read_bytes())
        cached_a = json.loads((OUTPUT / "extract" / f"{stem}.json").read_text(encoding="utf-8"))
        a = Extraction.model_validate(cached_a["extraction"])

        result = None if options.fresh else cached_second(stem, options.prompt)
        if result is None:
            if entry["split"] == "test" and not options.allow_test:
                print(f"\nskipped {stem}: test split (no new model call)")
                continue
            result = review_from_images(read.images, a.document_type, settings, options.prompt)
            (OUTPUT / options.prompt / f"{stem}.json").write_text(
                json.dumps({"reading": result.reading.model_dump(), "call": result.call.__dict__}),
                encoding="utf-8",
            )
            time.sleep(SECONDS_BETWEEN_CALLS)

        merged, agreement = compare_and_fill(a, result.reading, read.document)
        counts = Counter(agreement.values())
        right_a, wrong_a = compare(a, entry["fields"])
        right_b, wrong_b = compare(as_extraction(a.document_type, result.reading), entry["fields"])
        totals.update(counts)
        totals["a_right"] += len(right_a)
        totals["b_right"] += len(right_b)
        totals["fields"] += len(right_a) + len(wrong_a)
        c = result.call
        print(
            f"\n{stem}: A {len(right_a)}/{len(right_a) + len(wrong_a)} | "
            f"B {len(right_b)}/{len(right_b) + len(wrong_b)} | "
            f"{dict(counts)} | {c.input_tokens}+{c.output_tokens} tokens, {c.seconds}s"
        )
        for line in wrong_b:
            print(f"   B wrong  {line}")
        a_fields = dict(_flat(a))
        b_fields = dict(_flat_b(result.reading))
        for path, status in agreement.items():
            if status in ("differ", "filled", "missing"):
                print(f"   {status:8} {path}: A={a_fields.get(path)!r} B={b_fields.get(path)!r}")

    print(
        f"\nTOTAL fields: A right {totals['a_right']}/{totals['fields']}, "
        f"B right {totals['b_right']}/{totals['fields']} | compared fields: "
        f"agree {totals['agree']}, differ {totals['differ']}, "
        f"missing {totals['missing']}, filled {totals['filled']}"
    )


def _flat(a: Extraction):
    from app.pipeline.agreement import _a_values

    return ((path, field.value) for path, field in _a_values(a).items())


def _flat_b(b: SecondReading):
    from app.pipeline.agreement import _b_values

    return _b_values(b).items()


if __name__ == "__main__":
    main()
