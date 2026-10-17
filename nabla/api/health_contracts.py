"""Explicit liveness, readiness, and deep-diagnostic health contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.engine import Engine

from nabla.api.health_checks import check_postgres_sql, check_redis_ping
from nabla.api.runtime_environment import runtime_mode
from nabla.app_features import AppFeatures, disabled_subsystem_check
from nabla.utils.environment import env_bool

_READINESS_TIMEOUT_SECONDS = 3.0
# Each deployed runtime uses exactly one database backend (never both):
# FastAPI Cloud runs on Supabase, the TrueNAS homelab on PostgreSQL. Both need
# Redis. A developer workstation (runtime mode "local") requires nothing.
_REQUIRED_CHECKS_BY_RUNTIME_MODE = {
    "fastapi_cloud": frozenset({"redis", "supabase"}),
    "homelab": frozenset({"redis", "postgres"}),
}
# An explicit `<NAME>_REQUIRED=true|false` always wins over the runtime default.
_REQUIRED_OVERRIDES = {
    "postgres": "POSTGRES_REQUIRED",
    "redis": "REDIS_REQUIRED",
    "supabase": "SUPABASE_REQUIRED",
}


def required_dependencies() -> frozenset[str]:
    """Return the dependency checks whose failure makes the service not ready/unhealthy."""
    defaults = _REQUIRED_CHECKS_BY_RUNTIME_MODE.get(runtime_mode(), frozenset())
    return frozenset(name for name, variable in _REQUIRED_OVERRIDES.items() if env_bool(variable, name in defaults))


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


def _readiness_failure_stage(check: dict[str, Any]) -> str | None:
    """Classify sanitized readiness failures from existing check evidence."""
    if check.get("reachable") is not False:
        return None
    message = str(check.get("error") or check.get("reason") or "").casefold()
    if any(
        marker in message
        for marker in (
            "temporary failure in name resolution",
            "name or service not known",
            "getaddrinfo",
        )
    ):
        return "dns"
    if "authentication" in message or "password" in message:
        return "authentication"
    if "connection refused" in message:
        return "connection_refused"
    if "timeout" in message or "budget exceeded" in message:
        return "timeout"
    if "ssl" in message or "certificate" in message:
        return "tls"
    return "dependency"


def build_liveness_payload(*, version: str) -> dict[str, Any]:
    """Describe process liveness without performing network or database I/O."""
    return {
        "contract": "liveness",
        "status": "alive",
        "version": version,
        "checked_at": _timestamp(),
    }


async def _disabled_check(subsystem: str) -> dict[str, Any]:
    return disabled_subsystem_check(subsystem)


async def build_readiness_payload(
    *,
    redis_client: Any,
    engine: Engine | None,
    version: str,
    features: AppFeatures | None = None,
) -> tuple[dict[str, Any], bool]:
    """Check only dependencies required to serve normal application traffic.

    Subsystems disabled in ``features`` are reported as ``disabled`` without any
    connection attempt and never fail readiness; enabled ones are probed as before.
    """
    selected = features or AppFeatures()
    postgres_probe = run_in_threadpool(check_postgres_sql, engine) if selected.database else _disabled_check("database")
    redis_probe = check_redis_ping(redis_client) if selected.redis else _disabled_check("redis")
    try:
        async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
            postgres, redis = await asyncio.gather(postgres_probe, redis_probe)
    except TimeoutError:
        budget_exceeded = {
            "reachable": False,
            "error": f"readiness budget exceeded ({_READINESS_TIMEOUT_SECONDS:.0f}s)",
        }
        postgres = budget_exceeded if selected.database else disabled_subsystem_check("database")
        redis = budget_exceeded if selected.redis else disabled_subsystem_check("redis")

    checks = {"postgres": postgres, "redis": redis}
    required = required_dependencies()
    for name, check in checks.items():
        check["required"] = name in required
        stage = _readiness_failure_stage(check)
        if stage is not None:
            check.setdefault("failure_stage", stage)

    def usable(check: dict[str, Any]) -> bool:
        return check.get("skipped") is True or check.get("reachable") is True

    ready = all(usable(check) for name, check in checks.items() if name in required)
    degraded = ready and not all(usable(check) for check in checks.values())
    return (
        {
            "contract": "readiness",
            "status": "degraded" if degraded else "ready" if ready else "not_ready",
            "version": version,
            "checked_at": _timestamp(),
            "checks": checks,
            "subsystems": selected.subsystem_states(),
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
    cloudflare_refresh_unconfirmed = name == "cloudflare" and (check.get("stale") is True or bool(str(check.get("refresh_error") or "").strip()))
    cloudflare_unconfirmed = name == "cloudflare" and (cloudflare_refresh_unconfirmed or (check.get("reachable") is not True and not cloudflare_inventory_observed))
    if not timed_out and not cloudflare_unconfirmed:
        return normalized

    original_error = str(
        check.get("refresh_error") or check.get("error") or check.get("reason") or "",
    ).strip()
    if name == "cloudflare" and cloudflare_inventory_observed:
        normalized["last_known_reachable"] = check.get("reachable")
    normalized["reachable"] = None
    normalized["degraded"] = False
    normalized["status_confirmed"] = False
    normalized["severity"] = "warning"
    normalized["effective_state"] = "warn"
    if name == "cloudflare":
        warning = "⚠️ Cloudflare global status could not be confirmed; control-plane data is unavailable, stale, or the probe timed out."
    else:
        warning = "⚠️ Probe result is unknown because the optional diagnostic deadline was exceeded."
    normalized["warning"] = warning
    normalized["error"] = f"{warning} {original_error}".strip()
    if check.get("skipped") is True:
        normalized["reason"] = normalized["error"]
    return normalized


def apply_diagnostic_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Make deep-diagnostic state explicit without changing its HTTP contract."""
    raw_checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    required = required_dependencies()
    checks = {key: (value if key in required or not isinstance(value, dict) else _normalize_optional_uncertainty(key, value)) for key, value in raw_checks.items()}
    required_failed = any(isinstance(checks.get(key), dict) and checks[key].get("reachable") is False for key in required)
    optional_failed = any(check.get("reachable") is False for key, check in checks.items() if key not in required and isinstance(check, dict))
    status = "unhealthy" if required_failed else "degraded" if optional_failed else "healthy"
    return {
        **payload,
        "checks": checks,
        "contract": "deep_diagnostic",
        "status": status,
    }
