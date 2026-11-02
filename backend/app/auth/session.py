"""Signed session token for the shared-password gate. Pure functions, no HTTP."""

import hashlib
import hmac
import time


def _sign(secret: str, expires_at: int) -> str:
    return hmac.new(secret.encode(), f"session:{expires_at}".encode(), hashlib.sha256).hexdigest()


def make_token(secret: str, lifetime_seconds: int, now: float | None = None) -> str:
    expires_at = int((time.time() if now is None else now) + lifetime_seconds)
    return f"{expires_at}.{_sign(secret, expires_at)}"


def is_valid_token(secret: str, token: str | None, now: float | None = None) -> bool:
    if not token:
        return False
    expires_text, _, signature = token.partition(".")
    if not expires_text.isdigit() or not signature:
        return False
    expires_at = int(expires_text)
    if expires_at < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(signature, _sign(secret, expires_at))


def password_matches(expected: str, given: str) -> bool:
    """Constant-time compare (digests first, so lengths do not leak)."""
    return hmac.compare_digest(
        hashlib.sha256(expected.encode()).digest(), hashlib.sha256(given.encode()).digest()
    )
