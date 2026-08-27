"""Shared component-health composition for public and deep health endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.engine import Engine

from nabla.api.health_checks import (
    check_postgres_sql,
    check_redis_ping,
    check_supabase_http,
)
from nabla.api.homelab_health import build_homelab_health_payload
from nabla.api.platform_health import check_cloudflare_tunnels, check_pfsense_api

CORE_COMPONENT_KEYS = ("postgres", "redis", "supabase")
PLATFORM_COMPONENT_KEYS = ("truenas", "cloudflare", "pfsense")


def _truenas_component(snapshot: dict[str, Any]) -> dict[str, Any]:
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
        run_in_threadpool(check_postgres_sql, engine),
        check_redis_ping(redis_client),
        check_supabase_http(),
        homelab_probe,
        check_cloudflare_tunnels(),
        check_pfsense_api(),
    )
    return {
        "postgres": postgres,
        "redis": redis,
        "supabase": supabase,
        "truenas": _truenas_component(homelab),
        "cloudflare": cloudflare,
        "pfsense": pfsense,
    }


def component_status(components: dict[str, dict[str, Any]]) -> str:
    """Return required-core status without making optional platforms fatal."""
    for key in CORE_COMPONENT_KEYS:
        check = components.get(key, {})
        if check.get("skipped") is True:
            continue
        if check.get("reachable") is False:
            return "unhealthy"

    for key in PLATFORM_COMPONENT_KEYS:
        check = components.get(key, {})
        if check.get("skipped") is True:
            continue
        if check.get("reachable") is False or check.get("state") == "warn":
            return "degraded"
    return "healthy"
