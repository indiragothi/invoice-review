"""M3 walkthrough: the 7 dev samples through the RUNNING server with the real model.

Start the server first (from backend/):

    uv run --locked --no-sync uvicorn app.main:create_app --factory --port 8000

Then (from backend/):

    uv run --locked --no-sync python ../playground/walkthrough_live.py

It uses live Gemini calls: per document extraction + ledger (+ the second reading when a required
field is in doubt), and one correction-email draft. The test-split documents are NOT sent
(docs/evaluation.md). Results are checked against manifest.json. Downloads go to
playground/output/walkthrough/ so the CSV and XLSX can be opened by hand.
"""

import json
import sys
import time
from pathlib import Path

import httpx
import pymupdf

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG  # noqa: E402

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "output" / "walkthrough"
SECONDS_BETWEEN_UPLOADS = 9  # free tier: 15 requests per minute
results: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'OK ' if ok else 'BAD'} {label}{(': ' + detail) if detail else ''}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    dev = [d for d in manifest["documents"] if d["split"] == "dev"]
    http = httpx.Client(base_url=BASE, timeout=180)

    health = http.get("/health").json()
    check("server is up with the real model", health["status"] == "ok", health["model"])
    check(
        "3 clients and 13 ledgers",
        len(http.get("/api/clients").json()) == 3
        and len(http.get("/api/accounting/ledgers").json()) == 13,
    )
    check("the database starts empty", http.get("/api/documents").json() == [])

    # 1. upload the dev documents
    ids: dict[str, str] = {}
    calls = 0
    print("\n--- uploads (live Gemini) ---")
    for entry in dev:
        path = APP_CONFIG.samples_dir / entry["file"]
        started = time.perf_counter()
        r = http.post(
            "/api/documents",
            files={"file": (path.name, path.read_bytes())},
            data={"client_id": entry["client"]},
        )
        seconds = round(time.perf_counter() - started, 1)
        body = r.json()
        stem = path.stem
        if r.status_code != 201:
            check(f"{stem}: upload", False, f"HTTP {r.status_code} {body.get('detail')}")
            continue
        ids[stem] = body["id"]
        errors = sorted(i["code"] for i in body["issues"] if i["severity"] == "error")
        run = body["pipeline_run"]
        calls += run["calls"]
        boxes = sum(1 for f in body["review_data"]["fields"].values() if f["evidence"]["box"])
        ok = (
            body["status"] == entry["expected_status"]
            and errors == sorted(entry["expected_errors"])
            and body["ledger"]["suggested_code"] == entry["expected_ledger"]
            and boxes > 0
        )
        check(
            f"{stem}: {body['status']}",
            ok,
            f"errors {errors}, ledger {body['ledger']['suggested_code']} "
            f"(want {entry['expected_ledger']}), {boxes} fields with a box, "
            f"{run['calls']} calls, second reading ran {body['document_review']['ran']}, "
            f"{run['total_ms']} ms server time, {seconds}s",
        )
        time.sleep(SECONDS_BETWEEN_UPLOADS)
    print(f"live calls so far: {calls}")

    status = {d["id"]: d for d in http.get("/api/documents").json()}
    ready = [i for i, d in status.items() if d["status"] == "ready"]
    broken = [i for i, d in status.items() if d["status"] == "needs_review"]
    print(f"\nstored: {len(status)} documents, {len(ready)} ready, {len(broken)} needs_review")

    # 2. the safety invariant on the real server
    print("\n--- approval invariant ---")
    bad = ids["05-invalid-vendor-gstin"]
    http.put(f"/api/documents/{bad}/ledger", json={"ledger_code": "6140"})
    r = http.post(f"/api/documents/{bad}/decision", json={"decision": "approved"})
    check(
        "approve a needs_review document (ledger selected) -> 409",
        r.status_code == 409,
        r.json()["detail"],
    )
    first = ids["01-intra-classic"]
    r = http.post(f"/api/documents/{first}/decision", json={"decision": "approved"})
    check(
        "approve a ready document with no ledger selected -> 409",
        r.status_code == 409,
        r.json()["detail"],
    )

    # 3. fix the invalid GSTIN with the app's own suggestion, then approve
    print("\n--- fix, ledger, approve ---")
    doc = http.get(f"/api/documents/{bad}").json()
    suggestion = next(i["suggestion"] for i in doc["issues"] if i["code"] == "invalid_vendor_gstin")
    r = http.put(f"/api/documents/{bad}", json={"fields": {"vendor_gstin": suggestion}})
    check(
        "edit the GSTIN with the checksum suggestion -> ready",
        r.status_code == 200 and r.json()["status"] == "ready",
        f"{doc['review_data']['fields']['vendor_gstin']['value']} -> {suggestion}",
    )
    r = http.post(f"/api/documents/{bad}/decision", json={"decision": "approved"})
    check("approve it -> approved", r.status_code == 200 and r.json()["status"] == "approved")
    r = http.post(f"/api/documents/{bad}/decision", json={"decision": "rejected"})
    check("a decided record is locked -> 409", r.status_code == 409)

    # 4. correction email (1 live call)
    print("\n--- correction email (live Gemini, 1 call) ---")
    mail_doc = ids["08-buyer-not-client"]
    r = http.post(f"/api/documents/{mail_doc}/correction-email")
    if r.status_code == 200:
        mail = r.json()
        calls += 1
        (OUT / "correction-email.txt").write_text(
            f"Subject: {mail['subject']}\n\n{mail['body']}\n", encoding="utf-8"
        )
        check(
            "correction email draft for the wrong buyer -> 200",
            mail["issue_codes"] == ["buyer_not_client"] and "RP/RENT/26-27/07" in mail["subject"],
            mail["subject"],
        )
        print(mail["body"])
    else:
        check("correction email draft", False, f"HTTP {r.status_code} {r.text[:200]}")
    r = http.post(f"/api/documents/{ids['01-intra-classic']}/correction-email")
    check("no supplier-fixable issue -> 409", r.status_code == 409)

    # 5. bulk approve: confirm each suggested ledger, then approve all ready documents at once
    print("\n--- bulk approve ---")
    for doc_id in ready:
        d = http.get(f"/api/documents/{doc_id}").json()
        if d["status"] == "ready":
            http.put(
                f"/api/documents/{doc_id}/ledger",
                json={"ledger_code": d["ledger"]["suggested_code"]},
            )
    r = http.post("/api/documents/bulk-approve", json={"ids": list(ids.values())})
    body = r.json()
    approved_now = [d["id"] for d in body["approved"]]
    check(
        "bulk approve approves the ready ones and skips the rest with a reason",
        r.status_code == 200
        and set(approved_now) == set(ready) - {bad}
        and {s["id"] for s in body["skipped"]} >= set(broken),
        f"approved {len(approved_now)}, skipped {len(body['skipped'])}",
    )

    # 6. export
    print("\n--- export ---")
    csv_r = http.get("/api/export", params={"format": "csv"})
    xlsx_r = http.get("/api/export", params={"format": "xlsx"})
    (OUT / "approved.csv").write_bytes(csv_r.content)
    (OUT / "approved.xlsx").write_bytes(xlsx_r.content)
    rows = csv_r.content.decode("utf-8-sig").splitlines()
    approved_total = len(http.get("/api/documents", params={"status": "approved"}).json())
    check(
        "export has exactly the approved documents",
        len(rows) - 1 == approved_total and csv_r.status_code == 200 and xlsx_r.status_code == 200,
        f"{len(rows) - 1} rows",
    )

    # 7. files the server must refuse
    print("\n--- refused uploads ---")
    pdf = pymupdf.open()
    for _ in range(50):
        pdf.new_page()
    big = pdf.tobytes()
    r = http.post("/api/documents", files={"file": ("long.pdf", big)}, data={"client_id": "C001"})
    check("a 50-page PDF -> 413", r.status_code == 413, r.json()["detail"])
    r = http.post(
        "/api/documents",
        files={"file": ("bill.pdf", b"MZ" + b"\0" * 100)},
        data={"client_id": "C001"},
    )
    check("a program renamed .pdf -> 415", r.status_code == 415, r.json()["detail"])
    r = http.post(
        "/api/documents",
        files={"file": ("a.pdf", (APP_CONFIG.samples_dir / dev[0]["file"]).read_bytes())},
        data={"client_id": "C999"},
    )
    check("an unknown client -> 404", r.status_code == 404)

    docs = http.get("/api/documents").json()
    print(f"\nlive calls: {calls}; documents stored: {len(docs)}")
    print(f"WALKTHROUGH {sum(results)}/{len(results)} checks passed")
    print(f"files for you to open: {OUT}")


if __name__ == "__main__":
    main()
