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


def apply_diagnostic_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Make deep-diagnostic state explicit without changing its HTTP contract."""
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    required_failed = any(isinstance(checks.get(key), dict) and checks[key].get("reachable") is False for key in _REQUIRED_DIAGNOSTIC_CHECKS)
    optional_failed = any(check.get("reachable") is False for key, check in checks.items() if key not in _REQUIRED_DIAGNOSTIC_CHECKS and isinstance(check, dict))
    status = "unhealthy" if required_failed else "degraded" if optional_failed else "healthy"
    return {
        **payload,
        "contract": "deep_diagnostic",
        "status": status,
    }
