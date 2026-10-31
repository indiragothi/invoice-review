"""Experiment: run the reader over every sample and check what it sees.

For each sample it prints the text source, word count, lowest confidence and time, checks that
key values from manifest.json appear in the read text, and saves a debug image with every word
box drawn (green = PDF text layer, orange = OCR, red = OCR confidence below 0.90).

Run from backend/:

    uv run --locked --no-sync python ../playground/read_samples.py
"""

import json
import sys
import time
from pathlib import Path

from PIL import ImageDraw

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG  # noqa: E402
from app.reader import read_document  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"
LOW = 0.90


def indian(amount: str) -> str:
    whole, fraction = amount.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        whole = ",".join([*filter(None, groups), tail])
    return f"{whole}.{fraction}"


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"{'file':<30} {'source':<9} {'words':>5} {'min conf':>8} {'sec':>5}  missing")
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        started = time.perf_counter()
        result = read_document(path.read_bytes())
        seconds = time.perf_counter() - started
        doc = result.document

        compact = "".join(w.text for w in doc.words)
        fields = entry["fields"]
        wanted = {
            "vendor_gstin": fields.get("vendor_gstin"),
            "buyer_gstin": fields.get("buyer_gstin"),
            "invoice_number": fields["invoice_number"],
            "total": indian(fields["total"]),
        }
        missing = [name for name, value in wanted.items() if value and value not in compact]

        sources = "+".join(sorted({p.text_source for p in doc.pages}))
        lowest = min(w.confidence for w in doc.words)
        print(
            f"{path.name:<30} {sources:<9} {len(doc.words):>5} {lowest:>8.2f} {seconds:>5.1f}  "
            f"{', '.join(missing) or '-'}"
        )

        for page, image in zip(doc.pages, result.images, strict=True):
            canvas = image.copy()
            draw = ImageDraw.Draw(canvas)
            for word in doc.words:
                if word.page != page.number:
                    continue
                if page.text_source == "pdf_text":
                    colour = (0, 160, 0)
                else:
                    colour = (220, 0, 0) if word.confidence < LOW else (240, 140, 0)
                draw.rectangle(word.box, outline=colour, width=2)
            canvas.save(OUTPUT / f"{path.stem}-p{page.number}.png")
    print(f"Debug images: {OUTPUT}")


if __name__ == "__main__":
    main()
