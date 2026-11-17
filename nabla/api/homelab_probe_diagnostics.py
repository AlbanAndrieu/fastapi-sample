"""Stable, evidence-aware diagnostic categories for sampled probes."""

from __future__ import annotations

from typing import Any

_ACCESS_VERIFICATIONS = frozenset({"access_protected_origin_unverified"})
_ORIGIN_UNVERIFIED = frozenset({"origin_unverified", "authenticated_origin_unverified"})


def _edge_category(row: dict[str, Any], status: object) -> str | None:
    """Probe freshness, Access and origin-verification layers, checked first."""
    if row.get("probe_source") == "deadline" or row.get("timed_out") is True:
        return "DEADLINE"
    if row.get("probe_stale") is True:
        return "STALE"
    if row.get("cloudflare_service_token_rejected") is True:
        return "AUTH_FAILED"
    # F14 (16/11): the runner copies the anonymous Access signal onto authenticated rows,
    # so a 5xx past Access must be classified before ACCESS_PROTECTED hides it.
    if type(status) is int and status >= 500 and row.get("origin_reached") is True:
        return "ORIGIN_ERROR"
    if (
        row.get("public_probe_verification") in _ACCESS_VERIFICATIONS
        or row.get("public_probe_auth_mode") == "cloudflare_access_blocked"
        or row.get("cloudflare_access_signal") is True
        or row.get("cloudflare_default_deny") is True
    ):
        return "ACCESS_PROTECTED"
    if row.get("public_probe_verification") in _ORIGIN_UNVERIFIED:
        return "ORIGIN_UNVERIFIED"
    return None


def _transport_category(row: dict[str, Any]) -> str | None:
    """Network layer named by the probe error."""
    kind = str(row.get("error_kind") or row.get("error") or "").lower()
    if "timeout" in kind or "timed out" in kind:
        return "TIMEOUT"
    if "dns" in kind or "getaddrinfo" in kind or "nameresolution" in kind or "name resolution" in kind or row.get("dns_state") == "fail":
        return "DNS"
    if any(term in kind for term in ("tls", "ssl", "certificate")):
        return "TLS"
    if any(term in kind for term in ("connect", "socket", "refused")):
        return "TCP"
    return None


def classify_probe_diagnostic(row: dict[str, Any]) -> str | None:
    """Classify the observed layer without assuming an unverified origin is down."""
    status = row.get("http_status")
    category = _edge_category(row, status) or _transport_category(row)
    if category is not None:
        return category
    if row.get("application_error"):
        return "APPLICATION"
    if row.get("state") in {"fail", "warn"} and type(status) is int and status > 0:
        return "AUTH_REQUIRED" if status in {401, 403, 407} else "HTTP"
    if row.get("state") == "fail":
        return "CONNECT_FAILED" if row.get("reachable") is False else "UNKNOWN_FAILURE"
    if row.get("state") == "warn":
        return "UNCLASSIFIED_WARNING"
    return None
