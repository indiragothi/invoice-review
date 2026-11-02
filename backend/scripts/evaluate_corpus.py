"""Run the whole pipeline over `samples/` and report the metrics of docs/evaluation.md.

Answers of the model (reading A, ledger, reading B) are cached by the SHA-256 of the file, the
prompt version and the model in `evaluation/cache/`, so a second run costs nothing. Without
`--live` nothing is sent to the model: a document without a cached answer is reported as "not
evaluated". With `--live` the missing answers are asked for (free-tier pacing, `--max-calls`
stops the run). The test split needs `--allow-test`: it is for reported numbers only.

Run from backend/:

    uv run --locked --no-sync python -m scripts.evaluate_corpus                    # dev, cached
    uv run --locked --no-sync python -m scripts.evaluate_corpus --setup all        # 3 setups
    uv run --locked --no-sync python -m scripts.evaluate_corpus --split test --allow-test --live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.clients import CLIENTS_BY_ID
from app.config import APP_CONFIG, REPO_DIR, Settings, get_settings
from app.pipeline.base import PipelineContext, run_pipeline
from app.pipeline.steps import build_default_pipeline
from app.providers import (
    EXTRACT_PROMPT,
    LEDGER_PROMPT,
    REVIEW_PROMPT,
    CallInfo,
    ExtractionResult,
    LedgerResult,
    ProviderError,
    SecondReadingResult,
    extract,
    review_from_images,
    suggest_ledger,
)
from app.reader.cache import sha256_hex
from app.schemas.documents import Invoice, Receipt
from app.schemas.extraction import Extraction
from app.schemas.issues import Severity
from app.schemas.ledger import LedgerChoice
from app.schemas.second_reading import SecondReading
from app.validation.duplicates import invoice_key, receipt_key

TODAY = date(2026, 10, 31)  # the samples are dated Aug - Oct 2026
CACHE_DIR = REPO_DIR / "evaluation" / "cache"
LEGACY_DIR = REPO_DIR / "playground" / "output"  # answers from the playground, keyed by file stem
SECONDS_BETWEEN_CALLS = 4.5  # free tier: 15 requests per minute
SETUPS = {
    "never": "Gemini, reading A only",
    "on_doubt": "Gemini, A + B on doubt",
    "always": "Gemini, A + B always",
}
REQUIRED = {
    "invoice": ("vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "total"),
    "receipt": ("vendor_name", "invoice_date", "total"),
}
STRING_FIELDS = {"vendor_name", "buyer_name", "invoice_number"}
GSTIN_FIELDS = {"vendor_gstin", "buyer_gstin"}
AMOUNT_FIELDS = {"total", "round_off", "taxable_value", "cgst", "sgst", "igst"}


class NotCached(ProviderError):
    """No cached answer and `--live` was not given."""


# ---------------------------------------------------------------- cached model answers


class Answers:
    """Cached model answers, and live calls when allowed."""

    def __init__(self, settings: Settings, live: bool, max_calls: int) -> None:
        self.settings = settings
        self.live = live
        self.max_calls = max_calls
        self.live_calls = 0

    def _paths(self, kind: str, prompt: str, sha: str, stem: str) -> tuple[Path, Path]:
        own = CACHE_DIR / kind / f"{prompt}__{self.settings.active_model}" / f"{sha[:16]}.json"
        return own, LEGACY_DIR / prompt / f"{stem}.json"

    def load(self, kind: str, prompt: str, sha: str, stem: str) -> dict[str, Any] | None:
        own, legacy = self._paths(kind, prompt, sha, stem)
        for path in (own, legacy):
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data["call"]["model"] == self.settings.active_model:
                    return data
        return None

    def have(self, kind: str, prompt: str, sha: str, stem: str) -> bool:
        return self.load(kind, prompt, sha, stem) is not None

    def get(self, kind: str, prompt: str, sha: str, stem: str, ask) -> dict[str, Any]:
        cached = self.load(kind, prompt, sha, stem)
        if cached is not None:
            return cached
        if not self.live:
            raise NotCached(f"no cached {kind} answer for {stem} (run with --live)", busy=False)
        if self.live_calls >= self.max_calls:
            sys.exit(f"stopped: --max-calls {self.max_calls} reached")
        data = ask()
        self.live_calls += 1
        own, _ = self._paths(kind, prompt, sha, stem)
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text(json.dumps(data, indent=2), encoding="utf-8")
        time.sleep(SECONDS_BETWEEN_CALLS)
        return data

    # The three callables the pipeline takes. They know which document they belong to.

    def extractor(self, sha: str, stem: str):
        def run(reading) -> ExtractionResult:
            def ask() -> dict[str, Any]:
                result = extract(reading, self.settings)
                return {"extraction": result.extraction.model_dump(), "call": result.call.__dict__}

            data = self.get("extract", EXTRACT_PROMPT, sha, stem, ask)
            return ExtractionResult(
                Extraction.model_validate(data["extraction"]), CallInfo(**data["call"])
            )

        return run

    def ledger_suggester(self, sha: str, stem: str):
        def run(document, client_name) -> LedgerResult:
            def ask() -> dict[str, Any]:
                result = suggest_ledger(document, client_name, self.settings)
                return {"choice": result.choice.model_dump(), "call": result.call.__dict__}

            data = self.get("ledger", LEDGER_PROMPT, sha, stem, ask)
            return LedgerResult(LedgerChoice(**data["choice"]), CallInfo(**data["call"]))

        return run

    def second_reader(self, sha: str, stem: str):
        def run(images, document_type) -> SecondReadingResult:
            def ask() -> dict[str, Any]:
                result = review_from_images(images, document_type, self.settings)
                return {"reading": result.reading.model_dump(), "call": result.call.__dict__}

            data = self.get("review", REVIEW_PROMPT, sha, stem, ask)
            return SecondReadingResult(
                SecondReading.model_validate(data["reading"]), CallInfo(**data["call"])
            )

        return run


# ---------------------------------------------------------------- grading one document


def squash(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def alnum(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").casefold())


def dec(text: object) -> Decimal | None:
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError):
        return None


def leading_number(text: object) -> Decimal | None:
    match = re.match(r"\s*([0-9][0-9,]*\.?[0-9]*)", str(text or ""))
    return dec(match.group(1).replace(",", "")) if match else None


def tax_total(document: Invoice | Receipt, head: str) -> Decimal:
    return sum((t.amount or Decimal(0) for t in document.tax_lines if t.head == head), Decimal(0))


def got_value(document: Invoice | Receipt, name: str) -> tuple[bool, object]:
    """(applies, the document's value for a manifest field name)."""
    if isinstance(document, Invoice):
        simple = {
            "vendor_name": document.vendor_name,
            "vendor_gstin": document.vendor_gstin,
            "buyer_name": document.buyer_name,
            "buyer_gstin": document.buyer_gstin,
            "invoice_number": document.invoice_number,
            "total": document.total,
            "round_off": document.round_off,
            "taxable_value": document.taxable_value,
            "place_of_supply": document.place_of_supply_code,
        }
        when = document.invoice_date
    else:
        simple = {
            "vendor_name": document.merchant_name,
            "vendor_gstin": document.vendor_gstin,
            "invoice_number": document.receipt_number,
            "total": document.total,
            "round_off": document.round_off,
        }
        when = document.receipt_date
    if name == "invoice_date":
        return True, when.value.isoformat() if when.value else None
    if name in {"cgst", "sgst", "igst"}:
        return True, tax_total(document, name.upper())
    if name in simple:
        return True, simple[name]
    return False, None  # a field the document type does not have (for example buyer on a receipt)


def field_is_right(name: str, got: object, want: Any, ambiguous_ok: bool) -> bool:
    if name == "invoice_date":
        return got == want or ambiguous_ok
    if want is None:
        return got in (None, "")
    if name in STRING_FIELDS:
        return squash(str(got)) == squash(want)
    if name in GSTIN_FIELDS:
        return (str(got or "").replace(" ", "").upper()) == want
    if name in AMOUNT_FIELDS:
        value = Decimal(0) if got is None and name == "round_off" else got
        return isinstance(value, Decimal) and value == Decimal(want)
    return str(got) == str(want)  # place_of_supply code


def items_right(
    document: Invoice | Receipt, want_items: list[dict[str, str]]
) -> tuple[int, int, list[str]]:
    """(line items fully right, line items expected, what differs). Rows match by position."""
    invoice = isinstance(document, Invoice)
    right = 0
    notes: list[str] = []
    for index, want in enumerate(want_items):
        if index >= len(document.line_items):
            notes.append(f"line {index + 1}: missing")
            continue
        got = document.line_items[index]
        checks = {
            "description": (
                got.description,
                want["description"],
                squash(got.description) == squash(want["description"]),
            ),
            "quantity": (
                got.quantity,
                want["quantity"],
                leading_number(got.quantity) == leading_number(want["quantity"]),
            ),
            "rate": (got.rate, want["rate"], got.rate == dec(want["rate"])),
            "taxable_amount": (
                got.taxable_amount,
                want["taxable_amount"],
                got.taxable_amount == dec(want["taxable_amount"]),
            ),
        }
        if invoice:  # a receipt does not print HSN or GST rate per line
            checks["hsn_sac"] = (got.hsn_sac, want["hsn_sac"], got.hsn_sac == want["hsn_sac"])
            checks["gst_rate"] = (
                got.gst_rate,
                want["gst_rate"],
                got.gst_rate == dec(want["gst_rate"]),
            )
        bad = [f"{n} got {g!r} want {w!r}" for n, (g, w, ok) in checks.items() if not ok]
        right += not bad
        if bad:
            notes.append(f"line {index + 1}: " + ", ".join(bad))
    return right, len(want_items), notes


def evidence_contains(ctx: PipelineContext, name: str, want: Any) -> bool | None:
    """Provenance proxy: do the cited words contain the true value? None = not applicable."""
    if name not in {"vendor_name", "vendor_gstin", "invoice_number", "total"} or want is None:
        return None
    grounded = ctx.grounded.get(name)
    if grounded is None or grounded.grounding != "grounded" or not ctx.reading:
        return False
    words = {w.id: w.text for w in ctx.reading.words}
    cited = alnum("".join(words.get(i, "") for i in grounded.evidence))
    return alnum(str(want)) in cited


@dataclass
class DocResult:
    file: str
    split: str
    status: str = "failed"
    want_status: str = ""
    errors: set[str] = field(default_factory=set)
    want_errors: set[str] = field(default_factory=set)
    not_evaluated: str | None = None
    failure: str | None = None
    fields_right: int = 0
    fields_total: int = 0
    by_field: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
    wrong: list[str] = field(default_factory=list)
    required_right: bool = False
    items_right: int = 0
    items_total: int = 0
    item_notes: list[str] = field(default_factory=list)
    ledger_right: bool | None = None
    provenance: list[bool] = field(default_factory=list)
    calls: int = 0
    live_ran_b: bool = False
    seconds: float = 0.0
    tokens: int = 0
    violation: str | None = None


def grade(entry: dict[str, Any], ctx: PipelineContext, error: str | None) -> DocResult:
    sequence = entry.get("expected_when_original_exists") or {}
    result = DocResult(
        file=Path(entry["file"]).name,
        split=entry["split"],
        want_status=sequence.get("expected_status", entry["expected_status"]),
        want_errors=set(sequence.get("expected_errors", entry["expected_errors"])),
    )
    if error and "no cached" in error:
        result.not_evaluated = error
        return result
    result.failure = error
    result.status = ctx.status
    document, review = ctx.document, ctx.review
    for call in (ctx.call, ctx.ledger_call, ctx.second_call):
        if call is not None:
            result.calls += 1
            result.seconds += call.seconds
            result.tokens += call.input_tokens + call.output_tokens
    result.live_ran_b = ctx.second_call is not None
    if review is None or document is None:
        return result

    result.errors = {i.code.value for i in review.issues if i.severity == Severity.ERROR}
    kind = entry["type"]
    ambiguous_ok = "ambiguous_date" in result.want_errors
    for name, want in entry["fields"].items():
        if name == "line_items":
            continue
        applies, got = got_value(document, name)
        if not applies:
            continue
        ok = field_is_right(name, got, want, ambiguous_ok if name == "invoice_date" else False)
        result.by_field[name][1] += 1
        result.by_field[name][0] += ok
        result.fields_total += 1
        result.fields_right += ok
        if not ok:
            result.wrong.append(f"{name}: got {got!r}, want {want!r}")
        elif (hit := evidence_contains(ctx, name, want)) is not None:
            result.provenance.append(hit)
    result.required_right = all(
        field_is_right(
            n,
            got_value(document, n)[1],
            entry["fields"][n],
            ambiguous_ok if n == "invoice_date" else False,
        )
        for n in REQUIRED[kind]
    )
    result.items_right, result.items_total, result.item_notes = items_right(
        document, entry["fields"]["line_items"]
    )
    if ctx.ledger_call is not None and ctx.ledger is not None:
        result.ledger_right = ctx.ledger.suggested_code == entry["expected_ledger"]

    blocking = result.errors
    if ctx.status == "ready" and (blocking or result.want_errors):
        result.violation = (
            f"ready with errors {sorted(blocking)}, expected {sorted(result.want_errors)}"
        )
    return result


# ---------------------------------------------------------------- running a setup


def run_setup(
    mode: str,
    documents: list[dict[str, Any]],
    prerequisites: dict[str, dict[str, Any]],
    answers: Answers,
    base: Settings,
) -> list[DocResult]:
    settings = base.model_copy(update={"second_reading": mode})
    steps = build_default_pipeline()
    keys: dict[str, dict[str, Any]] = defaultdict(dict)  # client -> {file: duplicate key}
    results: list[DocResult] = []
    for entry in sorted([*documents, *prerequisites.values()], key=lambda e: e["file"]):
        path = APP_CONFIG.samples_dir / entry["file"]
        data = path.read_bytes()
        sha, stem, client = sha256_hex(data), path.stem, CLIENTS_BY_ID[entry["client"]]
        done = keys[client.id]
        ctx = PipelineContext(
            data=data,
            client=client,
            settings=settings,
            extractor=answers.extractor(sha, stem),
            ledger_suggester=answers.ledger_suggester(sha, stem),
            second_reader=answers.second_reader(sha, stem),
            today=TODAY,
            existing_keys=lambda kind, done=done: {  # type: ignore[misc]
                f: k for f, (t, k) in done.items() if t == kind
            },
        )
        ctx, error = run_pipeline(steps, ctx)
        if isinstance(ctx.document, Invoice) and (key := invoice_key(ctx.document)):
            done[entry["file"]] = ("invoice", key)
        elif isinstance(ctx.document, Receipt) and (key := receipt_key(ctx.document)):
            done[entry["file"]] = ("receipt", key)
        if entry["file"] in prerequisites and entry not in documents:
            continue
        results.append(grade(entry, ctx, error))
    return results


# ---------------------------------------------------------------- reporting


def pct(right: int, total: int) -> str:
    return f"{100 * right / total:.1f} % ({right}/{total})" if total else "n/a"


def report_setup(mode: str, results: list[DocResult]) -> list[str]:
    done = [r for r in results if r.not_evaluated is None]
    skipped = [r for r in results if r.not_evaluated is not None]
    lines = [f"### {SETUPS[mode]} (`SECOND_READING={mode}`)", ""]
    if skipped:
        lines += [
            f"**Not evaluated (no cached answer): {len(skipped)}** - "
            + ", ".join(r.file for r in skipped),
            "",
        ]
    if not done:
        return lines + ["No document could be evaluated.", ""]

    by_field: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in done:
        for name, (right, total) in r.by_field.items():
            by_field[name][0] += right
            by_field[name][1] += total
    errors_tp = sum(len(r.errors & r.want_errors) for r in done)
    errors_fn = sum(len(r.want_errors - r.errors) for r in done)
    errors_fp = sum(len(r.errors - r.want_errors) for r in done)
    ledger = [r.ledger_right for r in done if r.ledger_right is not None]
    prov = [p for r in done for p in r.provenance]
    items_right_n, items_total_n = (
        sum(r.items_right for r in done),
        sum(r.items_total for r in done),
    )
    violations = [r for r in done if r.violation]
    n = len(done)

    avg = lambda values: sum(values) / n  # noqa: E731
    fields_right, fields_total = (
        sum(r.fields_right for r in done),
        sum(r.fields_total for r in done),
    )
    safety = f"VIOLATED {len(violations)}" if violations else "holds, 0 violations"
    rows = [
        ("Field accuracy (all fields)", pct(fields_right, fields_total)),
        ("Line-item accuracy", pct(items_right_n, items_total_n)),
        ("Exact-document match (required fields)", pct(sum(r.required_right for r in done), n)),
        ("Status accuracy", pct(sum(r.status == r.want_status for r in done), n)),
        ("Error-code recall (expected codes found)", pct(errors_tp, errors_tp + errors_fn)),
        ("Error-code precision (found codes expected)", pct(errors_tp, errors_tp + errors_fp)),
        ("Ledger accuracy", pct(sum(ledger), len(ledger))),
        ("Provenance hit rate (proxy: cited words hold the true value)", pct(sum(prov), len(prov))),
        ("Seconds per document (model time of its calls)", f"{avg([r.seconds for r in done]):.1f}"),
        ("API calls per document", f"{avg([r.calls for r in done]):.2f}"),
        ("Tokens per document", f"{avg([r.tokens for r in done]):,.0f}"),
        ("Second reading ran on", f"{sum(r.live_ran_b for r in done)}/{n} documents"),
        ("**Safety invariant** (no blocking error ends `ready`)", f"**{safety}**"),
    ]
    lines += [f"Documents evaluated: **{n}**.", "", "| Metric | Result |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    lines.append("")
    for r in violations:
        lines.append(f"- VIOLATION `{r.file}`: {r.violation}")
    if violations:
        lines.append("")

    lines += ["Per field:", "", "| Field | Accuracy |", "|---|---|"]
    lines += [f"| {name} | {pct(*by_field[name])} |" for name in sorted(by_field)]

    lines += ["", "Documents that differ from the manifest:", ""]
    bad = [
        r
        for r in done
        if r.status != r.want_status
        or r.errors != r.want_errors
        or r.wrong
        or r.item_notes
        or r.failure
        or r.ledger_right is False
    ]
    for r in bad:
        parts = [f"status {r.status} (want {r.want_status})"]
        if r.errors != r.want_errors:
            parts.append(f"errors {sorted(r.errors)} (want {sorted(r.want_errors)})")
        if r.ledger_right is False:
            parts.append("ledger differs")
        if r.failure:
            parts.append(f"failed: {r.failure}")
        parts += r.wrong[:4]
        parts += r.item_notes[:3]
        lines.append(f"- `{r.file}` ({r.split}): " + "; ".join(parts))
    if not bad:
        lines.append("- none")

    worst = sorted(by_field.items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True)
    lines += ["", "Worst fields (wrong values, one example each):", ""]
    shown = 0
    for name, (right, total) in worst:
        if right == total or shown == 10:
            continue
        example = next(
            (f"`{r.file}`: {w}" for r in done for w in r.wrong if w.startswith(name + ":")), ""
        )
        lines.append(f"- **{name}** {total - right} wrong of {total}. {example}")
        shown += 1
    if shown == 0:
        lines.append("- none")
    lines.append("")
    return lines


def plan(documents, prerequisites, answers: Answers, modes: list[str]) -> int:
    """Print the cached / missing answers and return the largest number of live calls."""
    missing = {"extract": 0, "ledger": 0, "review": 0}
    for entry in [*documents, *prerequisites.values()]:
        path = APP_CONFIG.samples_dir / entry["file"]
        sha, stem = sha256_hex(path.read_bytes()), path.stem
        for kind, prompt in (
            ("extract", EXTRACT_PROMPT),
            ("ledger", LEDGER_PROMPT),
            ("review", REVIEW_PROMPT),
        ):
            if kind == "review" and not {"on_doubt", "always"} & set(modes):
                continue
            missing[kind] += not answers.have(kind, prompt, sha, stem)
    upper = missing["extract"] + missing["ledger"] + missing["review"]
    print(
        f"documents {len(documents)} (+{len(prerequisites)} needed first), model "
        f"{answers.settings.active_model}"
    )
    print(
        f"missing answers: reading A {missing['extract']}, ledger {missing['ledger']}, "
        f"reading B up to {missing['review']}  ->  at most {upper} live calls"
    )
    return upper


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--setup", choices=[*SETUPS, "all"], default="on_doubt")
    parser.add_argument("--live", action="store_true", help="ask the model for missing answers")
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    if options.split in {"test", "all"} and not options.allow_test:
        sys.exit("The test split is for reported numbers only: add --allow-test to use it.")

    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    by_file = {d["file"]: d for d in manifest["documents"]}
    documents = [d for d in manifest["documents"] if options.split in ("all", d["split"])]
    prerequisites = {  # the original of a duplicate must be seen first
        d["duplicate_of"]: by_file[d["duplicate_of"]]
        for d in documents
        if d.get("duplicate_of") and by_file[d["duplicate_of"]] not in documents
    }
    modes = list(SETUPS) if options.setup == "all" else [options.setup]
    settings = get_settings()
    answers = Answers(settings, options.live, options.max_calls)
    upper = plan(documents, prerequisites, answers, modes)
    if options.live and upper > options.max_calls:
        sys.exit(f"{upper} live calls could be needed, --max-calls is {options.max_calls}")

    started = time.time()
    lines = [
        f"# Evaluation results {date.today().isoformat()} ({options.split} split)",
        "",
        f"Model `{settings.active_model}`, prompts `{EXTRACT_PROMPT}`, `{LEDGER_PROMPT}`, "
        f"`{REVIEW_PROMPT}`, confidence threshold {APP_CONFIG.confidence_threshold}. "
        f"Corpus: {len(documents)} synthetic documents in this split; one document is "
        f"{100 / max(len(documents), 1):.1f} % of a figure, so read the numbers as a rough guide.",
        "",
    ]
    summary = [
        "| Setup | Field acc. | Exact-doc | Status acc. | Sec/doc | API calls/doc |",
        "|---|---|---|---|---|---|",
    ]
    blocks: list[str] = []
    for mode in modes:
        results = run_setup(mode, documents, prerequisites, answers, settings)
        done = [r for r in results if r.not_evaluated is None]
        n = max(len(done), 1)
        field_right = sum(r.fields_right for r in done)
        field_total = sum(r.fields_total for r in done)
        summary.append(
            f"| {SETUPS[mode]} | {pct(field_right, field_total)} "
            f"| {pct(sum(r.required_right for r in done), len(done))} "
            f"| {pct(sum(r.status == r.want_status for r in done), len(done))} "
            f"| {sum(r.seconds for r in done) / n:.1f} | {sum(r.calls for r in done) / n:.2f} |"
        )
        blocks += report_setup(mode, results)
    lines += [*summary, "", *blocks]
    lines.append(
        f"Live calls made in this run: {answers.live_calls}. "
        f"Run time {time.time() - started:.0f} s."
    )
    text = "\n".join(lines) + "\n"
    out = (
        options.out
        or REPO_DIR / "evaluation" / f"results-{date.today().isoformat()}-{options.split}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
