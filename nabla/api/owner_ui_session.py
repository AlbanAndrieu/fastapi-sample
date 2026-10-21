"""Short-lived HttpOnly authentication for the FastAPI owner diagnostics UI.

Never store DIAGNOSTICS_ACCESS_KEY in a cookie, page or localStorage.
Owner CIDR is mandatory on every read, even after a session is issued.
"""
from __future__ import annotations

import hmac
import re
import secrets
import time
from hashlib import sha256
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from nabla.config_settings import get_settings
from nabla.homelab_trusted_ip import allowed_owner_source

COOKIE_NAME = "__Host-nabla-ops"
SESSION_SECONDS = 1200
_DENY_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow",
}
_TOKEN_NONCE = re.compile(r"^[0-9a-f]{32}$")
_TOKEN_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


def _secret(settings: object) -> str | None:
    value = getattr(settings, "diagnostics_access_key", None)
    return value.get_secret_value() if isinstance(value, SecretStr) else None


def _signature(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        ("nabla:owner-ui-session:v1:" + payload).encode("ascii"),
        sha256,
    ).hexdigest()


def create_owner_cookie(secret: str, *, now: int | None = None) -> str:
    issued = int(time.time()) if now is None else now
    payload = f"{issued}.{issued + SESSION_SECONDS}.{secrets.token_hex(16)}"
    return payload + "." + _signature(secret, payload)


def owner_cookie_valid(token: str | None, settings: object, *, now: int | None = None) -> bool:
    if not token or len(token) > 180:
        return False
    secret = _secret(settings)
    if not secret:
        return False
    parts = token.split(".")
    if (
        len(parts) != 4
        or not _TOKEN_NONCE.fullmatch(parts[2])
        or not _TOKEN_SIGNATURE.fullmatch(parts[3])
    ):
        return False
    try:
        issued, expiry = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    current = int(time.time()) if now is None else now
    if issued > current + 30 or expiry <= current or expiry != issued + SESSION_SECONDS:
        return False
    return hmac.compare_digest(parts[3], _signature(secret, ".".join(parts[:3])))


def owner_ui_authenticated(request: Request, settings: object) -> bool:
    return allowed_owner_source(request.scope, settings) and owner_cookie_valid(
        request.cookies.get(COOKIE_NAME), settings,
    )


def owner_cookie_write_allowed(request: Request) -> bool:
    """Forbid cross-site state changes with cookie authentication."""
    origin = request.headers.get("origin", "")
    host = request.headers.get("host", "")
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc == host
        and not parsed.username
        and not parsed.password
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
        and request.headers.get("sec-fetch-site", "same-origin") == "same-origin"
    )


def register_owner_ui_session_routes(app: FastAPI) -> None:
    """Exchange the owner key for a narrow, expiring HttpOnly browser session."""

    @app.get("/api/ui/session", include_in_schema=False)
    async def session_status(request: Request) -> JSONResponse:
        return JSONResponse(
            {"authenticated": owner_ui_authenticated(request, get_settings())},
            headers=_DENY_HEADERS,
        )

    @app.post("/api/ui/session", include_in_schema=False)
    async def session_login(request: Request) -> JSONResponse:
        settings = get_settings()
        secret = _secret(settings)
        if not secret:
            return JSONResponse(
                {"detail": "Operator authentication not configured", "code": "unconfigured"},
                status_code=503,
                headers=_DENY_HEADERS,
            )
        if not owner_cookie_write_allowed(request):
            return JSONResponse(
                {"detail": "Same-origin request required", "code": "origin_unverified"},
                status_code=403,
                headers=_DENY_HEADERS,
            )
        if not allowed_owner_source(request.scope, settings):
            # Never disclose source addresses, proxy hops or CIDR values.
            # Verify the trusted source BEFORE evaluating any submitted key
            # to keep the login oracle unavailable to untrusted networks.
            return JSONResponse(
                {"detail": "Owner network not authorized", "code": "source_unverified"},
                status_code=403,
                headers=_DENY_HEADERS,
            )
        supplied = request.headers.get("X-Diagnostics-Key", "")
        if not supplied or not hmac.compare_digest(supplied, secret):
            return JSONResponse(
                {"detail": "Unauthorized"}, status_code=401, headers=_DENY_HEADERS,
            )
        response = JSONResponse({"authenticated": True}, headers=_DENY_HEADERS)
        response.set_cookie(
            COOKIE_NAME,
            create_owner_cookie(secret),
            max_age=SESSION_SECONDS,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.post("/api/ui/session/logout", include_in_schema=False)
    async def session_logout(request: Request) -> JSONResponse:
        if not owner_cookie_write_allowed(request):
            return JSONResponse(
                {"detail": "Same-origin request required"}, status_code=403, headers=_DENY_HEADERS,
            )
        response = JSONResponse({"authenticated": False}, headers=_DENY_HEADERS)
        response.delete_cookie(
            COOKIE_NAME, secure=True, httponly=True, samesite="strict", path="/",
        )
        return response
