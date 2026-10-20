"""Fail-closed protection for known operational HTTP routes.

Full REVIEW deny is staged behind OPS_ROUTE_POLICY_STRICT until the public
site migrates. This HTTP middleware does NOT authenticate WebSockets or ASGI
mounts; those transports need independent gates before exposing ops.
"""

from __future__ import annotations

from secrets import compare_digest
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from nabla.cloudflare_ops_access import (
    OwnerConfigError,
    OwnerKeysUnavailable,
    OwnerUnauthorized,
    assertion_from_headers,
    verify_owner_token,
)
from nabla.config_settings import get_settings
from nabla.route_policy import Credential, Visibility, route_policy_for

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request
    from starlette.responses import Response


_DENY_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow",
}


def _provided_access_key(request: Request, header_name: str) -> str:
    """Accept an endpoint-specific header or a legacy bearer token."""
    header_value = request.headers.get(header_name, "").strip()
    if header_value:
        return header_value
    authorization = request.headers.get("Authorization", "")
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


async def operations_access_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Protect recognized private paths even if their key is not configured."""
    policy = route_policy_for(request.url.path, method=request.method)
    settings = get_settings()

    if policy.visibility is Visibility.PUBLIC_CANDIDATE:
        return await call_next(request)
    if policy.visibility is Visibility.REVIEW:
        if getattr(settings, "ops_route_policy_strict", False):
            return JSONResponse(
                status_code=403,
                content={"detail": "Unapproved route"},
                headers=_DENY_HEADERS,
            )
        return await call_next(request)

    if policy.credential is Credential.ACCESS_JWT:
        try:
            subject = await verify_owner_token(assertion_from_headers(request.headers))
        except (OwnerConfigError, OwnerKeysUnavailable):
            return JSONResponse(
                status_code=503,
                content={"detail": "Owner identity provider unavailable"},
                headers=_DENY_HEADERS,
            )
        except OwnerUnauthorized:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid owner identity"},
                headers={**_DENY_HEADERS, "WWW-Authenticate": "Bearer"},
            )
        request.state.ops_owner_sub = subject
        return await call_next(request)

    key_fields = {
        Credential.ADMIN_KEY: ("admin_access_key", "X-Admin-Key"),
        Credential.DIAGNOSTICS_KEY: ("diagnostics_access_key", "X-Diagnostics-Key"),
        Credential.MCP_KEY: ("mcp_ops_key", "X-MCP-Key"),
    }
    field, header = key_fields[policy.credential]
    configured = getattr(settings, field, None)
    if configured is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Operational access unavailable"},
            headers=_DENY_HEADERS,
        )

    value = _provided_access_key(request, header)
    if not value or not compare_digest(value, configured.get_secret_value()):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid operational access key"},
            headers={**_DENY_HEADERS, "WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)
