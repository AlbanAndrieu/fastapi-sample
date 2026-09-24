"""Defensive copy helpers for cached homelab health payloads."""

from __future__ import annotations

from typing import Any, Literal


def copy_homelab_health_payload(
    payload: dict[str, Any],
    *,
    cache_source: Literal["origin", "memory"],
    cache_age_seconds: float,
    cache_ttl_seconds: float,
) -> dict[str, Any]:
    """Return a detached payload with explicit cache freshness metadata."""
    truenas = payload.get("truenas")
    truenas_copy = None
    if isinstance(truenas, dict):
        public = truenas.get("public")
        internal = truenas.get("internal")
        api = truenas.get("api")
        truenas_copy = {
            **truenas,
            "public": dict(public) if isinstance(public, dict) else public,
            "internal": dict(internal) if isinstance(internal, dict) else internal,
            "api": dict(api) if isinstance(api, dict) else api,
        }

    raw_summary = payload.get("probe_summary") or {}
    probe_summary = dict(raw_summary)
    for scope in ("public", "internal"):
        if isinstance(raw_summary.get(scope), dict):
            probe_summary[scope] = dict(raw_summary[scope])

    age = max(0.0, cache_age_seconds)
    return {
        **payload,
        "truenas": truenas_copy,
        "services": [
            dict(service)
            for service in payload.get("services", [])
        ],
        "public_probe_results": [
            dict(service)
            for service in payload.get("public_probe_results", [])
        ],
        "internal_services": [
            dict(service)
            for service in payload.get("internal_services", [])
        ],
        "probe_summary": probe_summary,
        "probe_cache": {
            "source": cache_source,
            "age_seconds": round(age, 3),
            "ttl_seconds": cache_ttl_seconds,
            "stale": age >= cache_ttl_seconds,
        },
    }
