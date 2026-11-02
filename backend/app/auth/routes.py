"""Shared-password gate: `/api/auth/*` and the `require_session` dependency.

With `APP_ACCESS_PASSWORD` unset the gate is off (local development) and everything is open.
"""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth.session import is_valid_token, make_token, password_matches
from app.config import APP_CONFIG, Settings

COOKIE_NAME = "invoice_review_session"

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionResponse(BaseModel):
    gate_enabled: bool
    authenticated: bool


class LoginRequest(BaseModel):
    password: str = Field(max_length=200)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _signed_in(request: Request, settings: Settings) -> bool:
    if settings.app_session_secret is None:
        return False
    return is_valid_token(
        settings.app_session_secret.get_secret_value(), request.cookies.get(COOKIE_NAME)
    )


def require_session(request: Request) -> None:
    """Guard for protected routes: 401 when the gate is on and the cookie is missing or invalid."""
    settings = _settings(request)
    if settings.auth_enabled and not _signed_in(request, settings):
        raise HTTPException(401, "Sign in to continue.")


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@router.get("/session", response_model=SessionResponse)
def session(request: Request) -> SessionResponse:
    settings = _settings(request)
    return SessionResponse(
        gate_enabled=settings.auth_enabled,
        authenticated=(not settings.auth_enabled) or _signed_in(request, settings),
    )


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, request: Request, response: Response) -> SessionResponse:
    settings = _settings(request)
    if settings.app_access_password is None or settings.app_session_secret is None:
        return SessionResponse(gate_enabled=False, authenticated=True)
    if not password_matches(settings.app_access_password.get_secret_value(), body.password):
        raise HTTPException(401, "Wrong password.")
    response.set_cookie(
        COOKIE_NAME,
        make_token(settings.app_session_secret.get_secret_value(), APP_CONFIG.session_seconds),
        max_age=APP_CONFIG.session_seconds,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )
    return SessionResponse(gate_enabled=True, authenticated=True)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
