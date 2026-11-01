"""Experiment: drive the HTTP API with FastAPI's TestClient. Offline, no API calls.

A temporary data folder and the cached model answers stand in for Gemini. Checks every route that
exists so far and its status codes (docs/api-and-pipeline.md). Run from backend/:

    uv run --locked --no-sync python ../playground/api_samples.py
"""

import json
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pipeline_samples import cached_extractor, cached_ledger_suggester  # noqa: E402

from app.config import APP_CONFIG  # noqa: E402
from app.main import create_app  # noqa: E402
from app.providers import CallInfo, ExtractionResult, ProviderError  # noqa: E402

WORK = Path(__file__).resolve().parent / "output" / "api_check"
results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'OK ' if ok else 'BAD'} {label}{(': ' + detail) if detail else ''}")


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = manifest["documents"]
    by_stem = {Path(d["file"]).stem: d for d in documents}
    mode = {"stem": "", "fail": None}  # which cached answer to use; how to misbehave

    def extractor(reading):
        if mode["fail"] == "busy":
            raise ProviderError("The AI provider is busy. Retry later.", busy=True)
        result = cached_extractor(mode["stem"])(reading)
        if mode["fail"] == "other":
            other = result.extraction.model_copy(update={"document_type": "other"})
            return ExtractionResult(extraction=other, call=CallInfo(**result.call.__dict__))
        return result

    def ledger(document, client_name):
        return cached_ledger_suggester(mode["stem"])(document, client_name)

    shutil.rmtree(WORK, ignore_errors=True)
    client = TestClient(create_app(WORK, extractor, ledger))

    def upload(path_or_bytes, name, client_id):
        data = path_or_bytes.read_bytes() if isinstance(path_or_bytes, Path) else path_or_bytes
        return client.post(
            "/api/documents", files={"file": (name, data)}, data={"client_id": client_id}
        )

    r = client.get("/health")
    check("GET /health", r.status_code == 200 and r.json()["status"] == "ok")
    r = client.get("/api/clients")
    check("GET /api/clients", r.status_code == 200 and len(r.json()) == 3, r.json()[0]["name"])
    r = client.get("/api/accounting/ledgers")
    check("GET /api/accounting/ledgers", r.status_code == 200 and len(r.json()) == 13)
    r = client.options(
        "/api/documents",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    check(
        "CORS allows the Vite origin",
        r.headers.get("access-control-allow-origin") == "http://localhost:5173",
    )

    # upload all 12
    ids, status_ok = {}, 0
    for entry in documents:
        path = APP_CONFIG.samples_dir / entry["file"]
        mode.update(stem=path.stem, fail=None)
        r = upload(path, path.name, entry["client"])
        ok = r.status_code == 201 and r.json()["status"] == entry["expected_status"]
        status_ok += ok
        if r.status_code == 201:
            ids[path.stem] = r.json()["id"]
    check("POST /api/documents x12 -> 201 and manifest status", status_ok == 12, f"{status_ok}/12")

    body = client.get(f"/api/documents/{ids['01-intra-classic']}").json()
    check(
        "GET /api/documents/{id}",
        body["status"] == "ready"
        and body["ledger"]["suggested_code"] == "6150"
        and "reading" not in body,
        f"ledger {body['ledger']['suggested_code']}, keys {len(body)}",
    )
    ready = client.get("/api/documents", params={"status": "ready"}).json()
    review = client.get("/api/documents", params={"status": "needs_review"}).json()
    c001 = client.get("/api/documents", params={"client_id": "C001"}).json()
    check(
        "GET /api/documents filters",
        (len(ready), len(review), len(c001)) == (8, 4, 10),
        f"ready {len(ready)}, needs_review {len(review)}, C001 {len(c001)}",
    )
    check(
        "list is newest first",
        [d["id"] for d in client.get("/api/documents").json()][0] == ids["12-restaurant-receipt"],
    )
    check(
        "bad status filter -> 422",
        client.get("/api/documents", params={"status": "nope"}).status_code == 422,
    )

    sample = APP_CONFIG.samples_dir / by_stem["01-intra-classic"]["file"]
    r = client.get(f"/api/documents/{ids['01-intra-classic']}/file")
    check(
        "GET .../file returns the original bytes",
        r.content == sample.read_bytes()
        and r.headers["content-type"] == "application/pdf"
        and r.headers["x-content-type-options"] == "nosniff",
    )
    r = client.get(f"/api/documents/{ids['01-intra-classic']}/pages/1")
    check(
        "GET .../pages/1 is a PNG", r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    )
    check(
        "page 2 of a 1-page file -> 404",
        client.get(f"/api/documents/{ids['01-intra-classic']}/pages/2").status_code == 404,
    )
    check(
        "page 2 of the 2-page invoice -> 200",
        client.get(f"/api/documents/{ids['09-two-page']}/pages/2").status_code == 200,
    )
    check("unknown document -> 404", client.get("/api/documents/nope").status_code == 404)

    # rejected uploads
    mode["stem"] = "01-intra-classic"
    before = len(client.get("/api/documents").json())
    pdf = pymupdf.open()
    for _ in range(APP_CONFIG.max_pages + 1):
        pdf.new_page()
    six_pages = pdf.tobytes()
    cases = {
        "renamed .exe -> 415": (upload(b"MZ" + b"\0" * 80, "bill.pdf", "C001"), 415),
        "over 5 MB -> 413": (
            upload(b"%PDF-" + b"0" * APP_CONFIG.max_upload_bytes, "big.pdf", "C001"),
            413,
        ),
        "6 pages -> 413": (upload(six_pages, "long.pdf", "C001"), 413),
        "unknown client -> 404": (upload(sample, "x.pdf", "C999"), 404),
    }
    for label, (response, want) in cases.items():
        check(label, response.status_code == want, response.json().get("detail", ""))
    check("rejections store nothing", len(client.get("/api/documents").json()) == before)
    check(
        "a path in the file name is not used",
        upload(sample, "../../evil.pdf", "C001").status_code == 201
        and not any("evil" in p.name for p in (WORK / "uploads").iterdir()),
    )

    # failures that are saved
    other = APP_CONFIG.samples_dir / by_stem["04-inter-compact"]["file"]
    client.delete(f"/api/documents/{ids['04-inter-compact']}")
    mode.update(stem="04-inter-compact", fail="busy")
    r = upload(other, other.name, by_stem["04-inter-compact"]["client"])
    failed_id = r.json()["document"]["id"]
    check(
        "provider failure -> 502, record saved as failed",
        r.status_code == 502
        and client.get(f"/api/documents/{failed_id}").json()["status"] == "failed",
        r.json()["detail"],
    )
    mode["fail"] = None
    check(
        "retry a non-failed document -> 409",
        client.post(f"/api/documents/{ids['01-intra-classic']}/retry").status_code == 409,
    )
    r = client.post(f"/api/documents/{failed_id}/retry")
    check(
        "retry the failed one -> 200 ready", r.status_code == 200 and r.json()["status"] == "ready"
    )
    mode["fail"] = "other"
    r = upload(sample, "notbill.pdf", "C002")
    check(
        "not an invoice or receipt -> 422, saved as failed",
        r.status_code == 422 and r.json()["document"]["status"] == "failed",
        r.json()["detail"],
    )

    # delete
    victim = ids["12-restaurant-receipt"]
    stored = {p.name for p in (WORK / "uploads").iterdir()}
    r = client.delete(f"/api/documents/{victim}")
    gone = client.get(f"/api/documents/{victim}").status_code == 404
    check(
        "DELETE -> 204, then 404, file removed",
        r.status_code == 204
        and gone
        and len({p.name for p in (WORK / "uploads").iterdir()}) == len(stored) - 1,
    )
    check("DELETE unknown -> 404", client.delete("/api/documents/nope").status_code == 404)

    print(f"\nAPI {sum(results)}/{len(results)} checks passed")


if __name__ == "__main__":
    main()
