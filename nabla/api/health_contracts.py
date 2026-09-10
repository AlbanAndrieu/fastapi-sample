"""Explicit liveness, readiness, and deep-diagnostic health contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.engine import Engine

from nabla.api.health_checks import check_postgres_sql, check_redis_ping

_READINESS_TIMEOUT_SECONDS = 3.0
_REQUIRED_DIAGNOSTIC_CHECKS = frozenset({"postgres", "redis", "supabase"})
_CLOUDFLARE_INVENTORY_FIELDS = frozenset(
    {
        "tunnel_count",
        "healthy_tunnels",
        "unhealthy_tunnels",
        "tunnel_statuses",
    },
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_liveness_payload(*, version: str) -> dict[str, Any]:
    """Describe process liveness without performing network or database I/O."""
    return {
        "contract": "liveness",
        "status": "alive",
        "version": version,
        "checked_at": _timestamp(),
    }


async def build_readiness_payload(
    *,
    redis_client: Any,
    engine: Engine,
    version: str,
) -> tuple[dict[str, Any], bool]:
    """Check only dependencies required to serve normal application traffic."""
    try:
        async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
            postgres, redis = await asyncio.gather(
                run_in_threadpool(check_postgres_sql, engine),
                check_redis_ping(redis_client),
            )
    except TimeoutError:
        postgres = redis = {
            "reachable": False,
            "error": f"readiness budget exceeded ({_READINESS_TIMEOUT_SECONDS:.0f}s)",
        }

    checks = {"postgres": postgres, "redis": redis}
    ready = all(check.get("skipped") is True or check.get("reachable") is True for check in checks.values())
    return (
        {
            "contract": "readiness",
            "status": "ready" if ready else "not_ready",
            "version": version,
            "checked_at": _timestamp(),
            "checks": checks,
        },
        ready,
    )


def _normalize_optional_uncertainty(
    name: str,
    check: dict[str, Any],
) -> dict[str, Any]:
    """Keep missing optional evidence distinct from an observed outage.

    A deadline only proves that the observer did not finish. Likewise, a
    Cloudflare control-plane retrieval failure, skipped observer, or stale
    last-known-good inventory cannot establish current global Cloudflare health.
    Preserve diagnostic context, add an explicit warning, and mark current
    reachability unknown instead of degraded/down.
    """
    normalized = dict(check)
    timed_out = check.get("timed_out") is True or check.get("error_kind") == "deadline"
    cloudflare_inventory_observed = any(field in check for field in _CLOUDFLARE_INVENTORY_FIELDS)
    cloudflare_refresh_unconfirmed = name == "cloudflare" and (
        check.get("stale") is True or bool(str(check.get("refresh_error") or "").strip())
    )
    cloudflare_unconfirmed = name == "cloudflare" and (
        cloudflare_refresh_unconfirmed
        or (
            check.get("reachable") is not True
            and not cloudflare_inventory_observed
        )
    )
    if not timed_out and not cloudflare_unconfirmed:
        return normalized

    original_error = str(
        check.get("refresh_error")
        or check.get("error")
        or check.get("reason")
        or "",
    ).strip()
    if name == "cloudflare" and cloudflare_inventory_observed:
        normalized["last_known_reachable"] = check.get("reachable")
    normalized["reachable"] = None
    normalized["degraded"] = False
    normalized["status_confirmed"] = False
    normalized["severity"] = "warning"
    normalized["effective_state"] = "warn"
    if name == "cloudflare":
        warning = (
            "⚠️ Cloudflare global status could not be confirmed; control-plane data is unavailable, stale, or the probe timed out."
        )
    else:
        warning = (
            "⚠️ Probe result is unknown because the optional diagnostic deadline was exceeded."
        )
    normalized["warning"] = warning
    normalized["error"] = f"{warning} {original_error}".strip()
    if check.get("skipped") is True:
        normalized["reason"] = normalized["error"]
    return normalized


def apply_diagnostic_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Make deep-diagnostic state explicit without changing its HTTP contract."""
    raw_checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    checks = {
        key: (
            value
            if key in _REQUIRED_DIAGNOSTIC_CHECKS or not isinstance(value, dict)
            else _normalize_optional_uncertainty(key, value)
        )
        for key, value in raw_checks.items()
    }
    required_failed = any(
        isinstance(checks.get(key), dict) and checks[key].get("reachable") is False
        for key in _REQUIRED_DIAGNOSTIC_CHECKS
    )
    optional_failed = any(
        check.get("reachable") is False
        for key, check in checks.items()
        if key not in _REQUIRED_DIAGNOSTIC_CHECKS and isinstance(check, dict)
    )
    status = "unhealthy" if required_failed else "degraded" if optional_failed else "healthy"
    return {
        **payload,
        "checks": checks,
        "contract": "deep_diagnostic",
        "status": status,
    }
