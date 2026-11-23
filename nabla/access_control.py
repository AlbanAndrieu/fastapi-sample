"""Fail-closed protection for known operational HTTP routes.

Full REVIEW deny is staged behind OPS_ROUTE_POLICY_STRICT until the public
site migrates. This HTTP middleware does NOT authenticate WebSockets or ASGI
mounts; those transports need independent gates before exposing ops.
"""

from __future__ import annotations

from secrets import compare_digest
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from nabla.api.owner_ui_session import cloudflare_ui_owner, owner_cookie_write_allowed, owner_ui_authenticated
from nabla.cloudflare_ops_access import (
    OwnerConfigError,
    OwnerKeysUnavailable,
    OwnerUnauthorized,
    assertion_from_headers,
    verify_owner_token,
)
from nabla.config_settings import APIDeploymentSettings, get_settings
from nabla.diagnostics_readonly_mode import public_diagnostics_readonly_enabled
from nabla.homelab_trusted_ip import owner_source_permitted
from nabla.route_policy import Credential, RoutePolicy, Visibility, route_policy_for

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request
    from starlette.responses import Response


_DENY_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Robots-Tag": "noindex, nofollow",
}


# Explicit temporary read allowlist; unknown and future operational routes stay gated.
# Site machine v2 projections are never part of this anonymous rollback.
_TEMPORARY_READ_ROUTES = frozenset(
    {
        "/healthz",
        "/sickz",
        "/readyz",
        "/api/topology",
        "/api/topology-telemetry",
        "/api/health-board",
        "/api/homelab-topology",
        "/api/public-topology",
        "/api/runtime/topology",
        "/api/homelab/declared-services",
        "/api/homelab/runtime",
        "/api/homelab/status",
        "/api/homelab/health",
        "/api/homelab/probes",
    },
)


# Exactly what .github/workflows/master-smoke.yml reads after a deploy; nothing else.
_SMOKE_READ_ROUTES = frozenset(
    {
        "/healthz",
        "/api/runtime/topology",
        "/api/homelab/status",
        "/api/homelab/health",
    },
)
_SMOKE_KEY_MIN_LENGTH = 32


def _smoke_key_accepted(request: Request, settings: APIDeploymentSettings) -> bool:
    """Read-only CI smoke credential, distinct from the owner diagnostics key.

    It deliberately skips the owner CIDR check: hosted runners are never on the
    owner network. Any other route, method or a short key falls through.
    """
    if request.method.upper() not in {"GET", "HEAD"} or request.url.path not in _SMOKE_READ_ROUTES:
        return False
    configured = getattr(settings, "production_smoke_access_key", None)
    expected = configured.get_secret_value() if configured is not None else ""
    provided = request.headers.get("X-Smoke-Key", "").strip()
    return len(expected) >= _SMOKE_KEY_MIN_LENGTH and bool(provided) and compare_digest(provided, expected)


def _provided_access_key(request: Request, header_name: str) -> str:
    """Accept an endpoint-specific header or a legacy bearer token."""
    header_value = request.headers.get(header_name, "").strip()
    if header_value:
        return header_value
    authorization = request.headers.get("Authorization", "")
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


async def _authorize_owner(
    request: Request,
    settings: APIDeploymentSettings,
) -> Response | None:
    """Require a verified human JWT AND an approved network source."""
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
    if not owner_source_permitted(request.scope, settings):
        return JSONResponse(
            status_code=403,
            content={"detail": "Owner network not authorized"},
            headers=_DENY_HEADERS,
        )
    request.state.ops_owner_sub = subject
    return None


def _private(response: Response) -> Response:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _same_origin_denial(request: Request) -> Response | None:
    """Owner browser sessions (SSO or cookie) may only mutate from the same origin."""
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"} and not owner_cookie_write_allowed(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Same-origin mutation required"},
            headers=_DENY_HEADERS,
        )
    return None


def _keyless_read_allowed(request: Request, settings: APIDeploymentSettings) -> bool:
    """Reads unlocked without the route key: temporary rollback list or CI smoke key.

    The temporary rollback of the owner-only *read* gate admits no mutation,
    admin, MCP, metrics or private transport. Explicitly disable it with
    HOMELAB_PUBLIC_DIAGNOSTICS_READONLY=false.
    """
    temporary = request.method.upper() in {"GET", "HEAD"} and request.url.path in _TEMPORARY_READ_ROUTES and public_diagnostics_readonly_enabled()
    return temporary or _smoke_key_accepted(request, settings)


async def _policy_without_static_key(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    policy: RoutePolicy,
    settings: APIDeploymentSettings,
) -> Response | None:
    """Decide routes that need no static key; None means the key check follows."""
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
    if policy.credential in {Credential.GITHUB_WEBHOOK, Credential.FEDERATION_HMAC}:
        # The exact POST handler verifies the signature over bounded raw bytes.
        return await call_next(request)
    if policy.credential is Credential.ACCESS_JWT:
        denied = await _authorize_owner(request, settings)
        return denied if denied is not None else await call_next(request)
    # SSO grants only the existing OWNER diagnostics scope, never SERVICE or
    # INTERNAL credentials. The original network policy and CSRF guard remain.
    if _owner_diagnostics(policy) and await cloudflare_ui_owner(request, settings):
        return _same_origin_denial(request) or _private(await call_next(request))
    return None


def _owner_diagnostics(policy: RoutePolicy) -> bool:
    return policy.visibility is Visibility.OWNER and policy.credential is Credential.DIAGNOSTICS_KEY


async def operations_access_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Protect recognized private paths even if their key is not configured."""
    policy = route_policy_for(request.url.path, method=request.method)
    settings = get_settings()

    if _keyless_read_allowed(request, settings):
        return _private(await call_next(request))
    decided = await _policy_without_static_key(request, call_next, policy, settings)
    if decided is not None:
        return decided

    key_fields = {
        Credential.ADMIN_KEY: ("admin_access_key", "X-Admin-Key"),
        Credential.DIAGNOSTICS_KEY: ("diagnostics_access_key", "X-Diagnostics-Key"),
        Credential.METRICS_KEY: ("metrics_scrape_key", "X-Metrics-Key"),
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

    # Short-lived owner-browser cookie is scoped to diagnostics routes ONLY.
    # Every cookie-authenticated read still requires the trusted source CIDR.
    if _owner_diagnostics(policy) and owner_ui_authenticated(request, settings):
        return _same_origin_denial(request) or await call_next(request)

    value = _provided_access_key(request, header)
    if not value or not compare_digest(value, configured.get_secret_value()):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid operational access key"},
            headers={**_DENY_HEADERS, "WWW-Authenticate": "Bearer"},
        )
    # An IP allowlist supplements, but never replaces, the diagnostics key.
    if _owner_diagnostics(policy) and getattr(settings, "homelab_trusted_cidrs", "").strip() and not owner_source_permitted(request.scope, settings):
        return JSONResponse(
            status_code=403,
            content={"detail": "Owner network not authorized"},
            headers=_DENY_HEADERS,
        )
    return await call_next(request)
