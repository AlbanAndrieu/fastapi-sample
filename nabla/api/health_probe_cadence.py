"""Cadence and last-observation metadata for optional deep-health probes.

The health board refreshes core evidence frequently, but optional integrations do
not need the same origin-probe rate. This module keeps a process-local sanitized
result cache for optional probes so an active UI cannot repeatedly call external
providers. Required readiness checks continue to run on every deep-health origin
refresh.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Any

_DEFAULT_OPTIONAL_INTERVAL_SEC = 300.0
_LOCAL_SUPPORT_INTERVAL_SEC = 120.0
_UNCONFIGURED_INTERVAL_SEC = 900.0
_FAILURE_RETRY_INTERVAL_SEC = 60.0
_REQUIRED_INTERVAL_SEC = 30.0

_LOCAL_SUPPORT_PROBES = frozenset({"sentry", "datadog", "pyroscope", "litellm"})


@dataclass(slots=True)
class _ProbeEntry:
    result: dict[str, Any]
    observed_at: str
    recorded_at: float
    interval_seconds: float


_cache: dict[str, _ProbeEntry] = {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def configured_interval_seconds(probe_name: str) -> float:
    """Return the normal configured cadence for an optional integration."""
    if probe_name in _LOCAL_SUPPORT_PROBES:
        return _LOCAL_SUPPORT_INTERVAL_SEC
    return _DEFAULT_OPTIONAL_INTERVAL_SEC


def _interval_for_result(probe_name: str, result: dict[str, Any]) -> float:
    if result.get("skipped") is True:
        return _UNCONFIGURED_INTERVAL_SEC
    if result.get("reachable") is False:
        return _FAILURE_RETRY_INTERVAL_SEC
    return configured_interval_seconds(probe_name)


def _annotate(
    entry: _ProbeEntry,
    *,
    source: str,
    now: float,
    refresh_error: str | None = None,
) -> dict[str, Any]:
    age = max(0.0, now - entry.recorded_at)
    remaining = max(0.0, entry.interval_seconds - age)
    result = {
        **entry.result,
        "probe_source": source,
        "probe_observed_at": entry.observed_at,
        "probe_age_seconds": round(age, 3),
        "probe_interval_seconds": round(entry.interval_seconds, 3),
        "next_probe_in_seconds": round(remaining, 3),
    }
    if refresh_error:
        result["probe_refresh_error"] = refresh_error
    return result


def annotate_required_probe(
    probe_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Attach cadence metadata to a required probe without caching its result."""
    del probe_name
    now = time.monotonic()
    entry = _ProbeEntry(
        result=dict(result),
        observed_at=_utc_now(),
        recorded_at=now,
        interval_seconds=_REQUIRED_INTERVAL_SEC,
    )
    return _annotate(entry, source="origin", now=now)


async def run_cadenced_optional_probe(
    probe_name: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Return cached optional evidence until its service-specific cadence is due."""
    now = time.monotonic()
    previous = _cache.get(probe_name)
    if previous is not None and now - previous.recorded_at < previous.interval_seconds:
        return _annotate(previous, source="memory", now=now)

    result = await loader()
    now = time.monotonic()
    if result.get("timed_out") is True and previous is not None:
        return _annotate(
            previous,
            source="memory",
            now=now,
            refresh_error=str(result.get("error") or "optional probe deadline exceeded"),
        )

    entry = _ProbeEntry(
        result=dict(result),
        observed_at=_utc_now(),
        recorded_at=now,
        interval_seconds=_interval_for_result(probe_name, result),
    )
    _cache[probe_name] = entry
    return _annotate(entry, source="origin", now=now)


def probe_cadence_contract() -> dict[str, Any]:
    """Expose stable cadence values for diagnostics and UI documentation."""
    return {
        "required_seconds": _REQUIRED_INTERVAL_SEC,
        "local_optional_seconds": _LOCAL_SUPPORT_INTERVAL_SEC,
        "external_optional_seconds": _DEFAULT_OPTIONAL_INTERVAL_SEC,
        "failed_optional_retry_seconds": _FAILURE_RETRY_INTERVAL_SEC,
        "unconfigured_optional_seconds": _UNCONFIGURED_INTERVAL_SEC,
    }


def reset_probe_cadence_cache() -> None:
    """Clear optional evidence for deterministic tests."""
    _cache.clear()
