"""Experiment: the shared-password gate over HTTP with TestClient. Offline, no API calls.

Checks: gate off -> everything open; gate on -> 401 on every protected route without the cookie,
wrong password -> 401, right password -> cookie (HttpOnly, SameSite=Lax) and access, logout -> 401
again, a forged cookie -> 401, `/health` and `/api/auth/session` stay open. Run from backend/:

    uv run --locked --no-sync python ../playground/auth_samples.py
"""

import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.routes import COOKIE_NAME  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

WORK = Path(__file__).resolve().parent / "output" / "auth_check"
PASSWORD = "demo-password-for-check"
results: list[bool] = []

PROTECTED = [
    ("GET", "/api/clients"),
    ("GET", "/api/accounting/ledgers"),
    ("GET", "/api/documents"),
    ("GET", "/api/documents/nope"),
    ("GET", "/api/documents/nope/file"),
    ("GET", "/api/documents/nope/pages/1"),
    ("PUT", "/api/documents/nope"),
    ("PUT", "/api/documents/nope/ledger"),
    ("POST", "/api/documents"),
    ("POST", "/api/documents/bulk-approve"),
    ("POST", "/api/documents/nope/decision"),
    ("POST", "/api/documents/nope/retry"),
    ("POST", "/api/documents/nope/correction-email"),
    ("DELETE", "/api/documents/nope"),
    ("GET", "/api/export"),
]


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'OK ' if ok else 'BAD'} {label}{(': ' + detail) if detail else ''}")


def settings(password: str | None) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_api_key="not-a-real-key",
        gemini_model="not-a-real-model",
        app_access_password=password,
        app_session_secret="check-secret-check-secret" if password else None,
    )


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)

    # Gate off (local development)
    with TestClient(create_app(data_dir=WORK / "off", settings=settings(None))) as client:
        check(
            "gate off: session says open",
            client.get("/api/auth/session").json()
            == {"gate_enabled": False, "authenticated": True},
        )
        check("gate off: clients open", client.get("/api/clients").status_code == 200)

    # Gate on
    app = create_app(data_dir=WORK / "on", settings=settings(PASSWORD))
    with TestClient(app) as client:
        check(
            "gate on: session says signed out",
            client.get("/api/auth/session").json()
            == {"gate_enabled": True, "authenticated": False},
        )
        check("gate on: /health open", client.get("/health").status_code == 200)
        for method, path in PROTECTED:
            code = client.request(method, path).status_code
            check(f"no cookie: {method} {path}", code == 401, str(code))

        bad = client.post("/api/auth/login", json={"password": "wrong"})
        check(
            "wrong password -> 401, no cookie",
            bad.status_code == 401 and COOKIE_NAME not in bad.cookies,
        )
        check("missing password -> 422", client.post("/api/auth/login", json={}).status_code == 422)

        client.cookies.set(COOKIE_NAME, "9999999999.deadbeef")
        check("forged cookie -> 401", client.get("/api/clients").status_code == 401)
        client.cookies.clear()

        ok = client.post("/api/auth/login", json={"password": PASSWORD})
        header = ok.headers.get("set-cookie", "").lower()
        check(
            "right password -> 200 signed in", ok.status_code == 200 and ok.json()["authenticated"]
        )
        check(
            "cookie is HttpOnly + SameSite=Lax",
            "httponly" in header and "samesite=lax" in header,
            header,
        )
        check("cookie not Secure over plain http", "secure" not in header)
        check(
            "session says signed in",
            client.get("/api/auth/session").json()["authenticated"] is True,
        )
        check("clients open after login", client.get("/api/clients").status_code == 200)
        check("documents list after login", client.get("/api/documents").status_code == 200)
        check("export after login", client.get("/api/export").status_code == 200)

        https = client.post(
            "/api/auth/login", json={"password": PASSWORD}, headers={"x-forwarded-proto": "https"}
        )
        check(
            "behind HTTPS proxy the cookie is Secure",
            "secure" in https.headers.get("set-cookie", "").lower(),
        )

        out = client.post("/api/auth/logout")
        check("logout -> 204", out.status_code == 204)
        client.cookies.clear()  # TestClient keeps no cookie a browser would have deleted
        check("after logout -> 401", client.get("/api/clients").status_code == 401)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
