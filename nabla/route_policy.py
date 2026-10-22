"""Authoritative privacy classification for HTTP routes and inventory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Visibility(StrEnum):
    PUBLIC_CANDIDATE = "PUBLIC_CANDIDATE"
    OWNER = "OWNER"
    SERVICE = "SERVICE"
    INTERNAL = "INTERNAL"
    REVIEW = "REVIEW"


class Credential(StrEnum):
    NONE = "none"
    ADMIN_KEY = "admin_key"
    DIAGNOSTICS_KEY = "diagnostics_key"
    MCP_KEY = "mcp_key"
    ACCESS_JWT = "access_jwt"


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    """Desired disclosure and authorization requirements."""

    visibility: Visibility
    credential: Credential = Credential.NONE


PUBLIC = RoutePolicy(Visibility.PUBLIC_CANDIDATE)
REVIEW = RoutePolicy(Visibility.REVIEW)
DIAGNOSTIC = RoutePolicy(Visibility.OWNER, Credential.DIAGNOSTICS_KEY)
SITE_CATALOG = RoutePolicy(Visibility.SERVICE, Credential.DIAGNOSTICS_KEY)
OWNER = RoutePolicy(Visibility.OWNER, Credential.ACCESS_JWT)
ADMIN = RoutePolicy(Visibility.INTERNAL, Credential.ADMIN_KEY)
INTERNAL = RoutePolicy(Visibility.INTERNAL, Credential.DIAGNOSTICS_KEY)
MCP = RoutePolicy(Visibility.INTERNAL, Credential.MCP_KEY)
WEBSOCKET = RoutePolicy(Visibility.INTERNAL, Credential.ACCESS_JWT)

_PUBLIC = frozenset({"/health", "/livez", "/api/public-homelab/v1", "/api/ui/services"})
_DIAGNOSTIC_EXACT = frozenset(
    {
        "/api/homelab-services",
        "/api/homelab-topology",
        "/api/public-topology",
        "/api/runtime/topology",
        "/healthz",
        "/sickz",
        "/readyz",
        "/sentry-debug",
    },
)


def within(path: str, prefix: str) -> bool:
    """Use segment boundaries, not unsafe startswith('/admin')."""
    return path == prefix or path.startswith(prefix + "/")


_READ_METHODS = frozenset({"GET", "HEAD"})
# Evaluated in order; the first matching segment prefix wins.
_PREFIX_POLICIES: tuple[tuple[str, RoutePolicy], ...] = (
    ("/private/ops", OWNER),
    ("/a2a", OWNER),
    ("/admin", ADMIN),
    ("/mcp", MCP),
    ("/metrics", INTERNAL),
)


def _http_route_policy(path: str, method: str) -> RoutePolicy:
    if (path == "/api/ui/session" and method in {"GET", "HEAD", "POST"}) or (path == "/api/ui/session/logout" and method == "POST"):
        return PUBLIC
    if path in {"/api/site/catalog/v2", "/api/site/health/v2"} and method in _READ_METHODS:
        return SITE_CATALOG
    for prefix, policy in _PREFIX_POLICIES:
        if within(path, prefix):
            return policy
    if path in _DIAGNOSTIC_EXACT or within(path, "/api/homelab") or within(path, "/api/health-board"):
        return DIAGNOSTIC
    if method in _READ_METHODS and path in _PUBLIC:
        return PUBLIC
    return REVIEW


def route_policy_for(path: str, *, method: str = "GET", kind: str = "http") -> RoutePolicy:
    """Unknown routes require REVIEW, never implicit public approval."""
    if kind == "websocket":
        return WEBSOCKET if within(path, "/ws") else REVIEW
    if kind != "http":
        # Includes opaque mounts: their inner routes cannot be inventoried.
        return REVIEW
    return _http_route_policy(path, method.upper())
