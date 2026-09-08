"""Shared component-health composition for public and deep health endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from sqlalchemy.engine import Engine

from nabla.api.health_checks import (
    check_postgres_sql,
    check_redis_ping,
    check_supabase_http,
)
from nabla.api.homelab_health import build_homelab_health_payload
from nabla.api.platform_health import check_cloudflare_tunnels, get_pfsense_api_snapshot

CORE_COMPONENT_KEYS = ("postgres", "redis", "supabase")
CRITICAL_INFRA_COMPONENT_KEYS = ("unbound",)
PLATFORM_COMPONENT_KEYS = ("truenas", "cloudflare", "pfsense")


def truenas_component(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reduce the detailed TrueNAS snapshot to a component-level status."""
    truenas = snapshot.get("truenas")
    if not isinstance(truenas, dict):
        return {
            "reachable": None,
            "skipped": True,
            "reason": "TrueNAS health unavailable",
        }

    state = str(truenas.get("state") or "unknown")
    public = truenas.get("public") if isinstance(truenas.get("public"), dict) else {}
    internal = truenas.get("internal") if isinstance(truenas.get("internal"), dict) else None
    api = truenas.get("api") if isinstance(truenas.get("api"), dict) else None
    return {
        "reachable": state != "fail",
        "state": state,
        "public_reachable": public.get("reachable"),
        "internal_reachable": internal.get("reachable") if internal else None,
        "api_reachable": api.get("reachable") if api else None,
        "tls_trusted": public.get("tls_trusted"),
        "http_status": public.get("http_status"),
    }


def pfsense_unbound_component(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reduce reconciled pfSense DNS evidence to a critical Unbound component."""
    pfsense = snapshot.get("pfsense")
    dns = pfsense.get("dns") if isinstance(pfsense, dict) else None
    if not isinstance(dns, dict):
        return {
            "reachable": None,
            "state": "unknown",
            "critical": True,
            "skipped": True,
            "reason": "pfSense DNS Resolver health unavailable",
        }

    configured = dns.get("configured")
    policy_state = str(dns.get("policy_state") or "unknown")
    resolver = dns.get("resolver") if isinstance(dns.get("resolver"), dict) else {}
    result: dict[str, Any] = {
        "reachable": None,
        "state": policy_state,
        "critical": True,
        "required": True,
        "reason": dns.get("reason") or "pfSense DNS Resolver state is unknown",
        "resolver_running": resolver.get("running"),
        "resolver_enabled": resolver.get("enabled"),
        "stale": dns.get("stale") is True,
    }
    if configured is not True:
        result["skipped"] = True
        return result
    if result["stale"] is True:
        return result
    if policy_state == "fail":
        result["reachable"] = False
    elif policy_state in {"ok", "warn"}:
        result["reachable"] = True
    return result


async def build_component_checks(
    *,
    redis_client: Any,
    engine: Engine,
    homelab_snapshot: Awaitable[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build canonical core/platform checks, reusing a homelab probe when supplied."""
    homelab_probe = homelab_snapshot or build_homelab_health_payload()
    (
        postgres,
        redis,
        supabase,
        homelab,
        cloudflare,
        pfsense,
    ) = await asyncio.gather(
        asyncio.to_thread(check_postgres_sql, engine),
        check_redis_ping(redis_client),
        check_supabase_http(),
        homelab_probe,
        check_cloudflare_tunnels(),
        get_pfsense_api_snapshot(),
    )
    return {
        "postgres": postgres,
        "redis": redis,
        "supabase": supabase,
        "truenas": truenas_component(homelab),
        "cloudflare": cloudflare,
        "pfsense": pfsense,
    }


def _critical_infra_status(components: dict[str, dict[str, Any]]) -> str | None:
    """Return the strongest status contributed by critical infrastructure."""
    degraded = False
    for key in CRITICAL_INFRA_COMPONENT_KEYS:
        if key not in components:
            continue
        check = components[key]
        if check.get("skipped") is True:
            continue
        if check.get("stale") is True:
            degraded = True
            continue
        if check.get("reachable") is False or check.get("state") == "fail":
            return "unhealthy"
        if check.get("reachable") is None or check.get("state") in {"warn", "unknown"}:
            degraded = True
    return "degraded" if degraded else None


def component_status(components: dict[str, dict[str, Any]]) -> str:
    """Return required-core and critical-infrastructure health status."""
    for key in CORE_COMPONENT_KEYS:
        check = components.get(key, {})
        if check.get("skipped") is True:
            continue
        if check.get("reachable") is False:
            return "unhealthy"

    critical_status = _critical_infra_status(components)
    if critical_status == "unhealthy":
        return critical_status

    for key in PLATFORM_COMPONENT_KEYS:
        check = components.get(key, {})
        if check.get("skipped") is True:
            continue
        if check.get("reachable") is False or check.get("state") == "warn" or check.get("stale") is True or check.get("tls_trusted") is False:
            return "degraded"
    return critical_status or "healthy"
