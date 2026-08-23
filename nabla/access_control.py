"""Optional operational endpoint protection until an identity provider exists."""

from __future__ import annotations

from secrets import compare_digest
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from nabla.config_settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request
    from starlette.responses import Response


_DIAGNOSTIC_PATHS = frozenset(
    {
        "/api/homelab-services",
        "/api/homelab/health",
        "/healthz",
        "/metrics",
        "/sentry-debug",
        "/sickz",
    }
)


def _provided_access_key(request: Request, header_name: str) -> str:
    """Accept an endpoint-specific header or a standard bearer token."""
    header_value = request.headers.get(header_name, "").strip()
    if header_value:
        return header_value

    authorization = request.headers.get("Authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer":
        return value.strip()
    return ""


async def operations_access_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Protect configured operational surfaces without changing open defaults."""
    path = request.url.path
    settings = get_settings()

    if path == "/admin" or path.startswith("/admin/"):
        configured_key = settings.admin_access_key
        header_name = "X-Admin-Key"
    elif path in _DIAGNOSTIC_PATHS:
        configured_key = settings.diagnostics_access_key
        header_name = "X-Diagnostics-Key"
    else:
        return await call_next(request)

    if configured_key is None:
        return await call_next(request)

    provided_key = _provided_access_key(request, header_name)
    if not provided_key or not compare_digest(
        provided_key,
        configured_key.get_secret_value(),
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid operational access key"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)
