"""Bounded read-only core metrics projection for the homelab health board."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import math
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from nabla.utils.environment import env_bool

_DEFAULT_TIMEOUT_SECONDS = 2.5
_DEFAULT_CACHE_TTL_SECONDS = 30.0
_MIN_TIMEOUT_SECONDS = 0.5
_MAX_TIMEOUT_SECONDS = 5.0
_MIN_CACHE_TTL_SECONDS = 10.0
_MAX_CACHE_TTL_SECONDS = 300.0

_METRIC_SPECS: tuple[dict[str, str], ...] = (
    {
        "component": "truenas",
        "key": "memory_available_ratio",
        "metric": "nabla:core:truenas_memory_available_ratio",
        "unit": "ratio",
        "signal_type": "capacity",
    },
    {
        "component": "truenas",
        "key": "cpu_busy_ratio",
        "metric": "nabla:core:truenas_cpu_busy_ratio",
        "unit": "ratio",
        "signal_type": "saturation",
    },
    {
        "component": "truenas",
        "key": "node_telemetry_up",
        "metric": "nabla:telemetry:truenas_node_up",
        "unit": "boolean",
        "signal_type": "telemetry",
    },
    {
        "component": "truenas",
        "key": "container_telemetry_up",
        "metric": "nabla:telemetry:truenas_cadvisor_up",
        "unit": "boolean",
        "signal_type": "telemetry",
    },
    {
        "component": "pfsense",
        "key": "metrics_up",
        "metric": "nabla:telemetry:pfsense_metrics_up",
        "unit": "boolean",
        "signal_type": "telemetry",
    },
    {
        "component": "prometheus",
        "key": "self_up",
        "metric": "nabla:observability:prometheus_up",
        "unit": "boolean",
        "signal_type": "telemetry",
    },
)

_cache_lock = asyncio.Lock()
_cached_snapshot: dict[str, Any] | None = None
_cached_at = 0.0
_cached_url = ""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _bounded_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _settings() -> dict[str, Any]:
    enabled = env_bool("HOMELAB_CORE_METRICS_ENABLED", False)
    raw_url = os.getenv("HOMELAB_CORE_METRICS_URL", "").strip().rstrip("/")
    if not enabled:
        return {
            "enabled": False,
            "url": "",
            "timeout": _DEFAULT_TIMEOUT_SECONDS,
            "ttl": _DEFAULT_CACHE_TTL_SECONDS,
        }
    if not raw_url:
        return {
            "enabled": True,
            "url": "",
            "timeout": _DEFAULT_TIMEOUT_SECONDS,
            "ttl": _DEFAULT_CACHE_TTL_SECONDS,
        }

    parsed = urlsplit(raw_url)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return {
            "enabled": True,
            "url": "",
            "invalid_url": True,
            "timeout": _DEFAULT_TIMEOUT_SECONDS,
            "ttl": _DEFAULT_CACHE_TTL_SECONDS,
        }

    return {
        "enabled": True,
        "url": raw_url,
        "timeout": _bounded_float(
            "HOMELAB_CORE_METRICS_TIMEOUT_SECONDS",
            _DEFAULT_TIMEOUT_SECONDS,
            _MIN_TIMEOUT_SECONDS,
            _MAX_TIMEOUT_SECONDS,
        ),
        "ttl": _bounded_float(
            "HOMELAB_CORE_METRICS_CACHE_TTL_SECONDS",
            _DEFAULT_CACHE_TTL_SECONDS,
            _MIN_CACHE_TTL_SECONDS,
            _MAX_CACHE_TTL_SECONDS,
        ),
    }


def _disabled_snapshot(*, invalid_url: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "configured": False,
        "reachable": None,
        "complete": False,
        "stale": False,
        "source": "disabled",
        "generated_at": _utc_now(),
        "components": {},
        **({"configuration_error": "invalid_metrics_url"} if invalid_url else {}),
    }


def _parse_vector(payload: object) -> tuple[float | None, float | None]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("unexpected Prometheus response")
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        raise ValueError("expected Prometheus vector result")
    result = data.get("result")
    if not isinstance(result, list):
        raise ValueError("missing Prometheus vector result")
    if not result:
        return None, None
    if len(result) != 1 or not isinstance(result[0], dict):
        raise ValueError("recording rule must resolve to one series")
    sample = result[0].get("value")
    if not isinstance(sample, list) or len(sample) != 2:
        raise ValueError("invalid Prometheus sample")
    try:
        timestamp = float(sample[0])
        value = float(sample[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("non-numeric Prometheus sample") from exc
    if not math.isfinite(timestamp) or not math.isfinite(value):
        raise ValueError("non-finite Prometheus sample")
    return timestamp, value


async def _query_metric(
    client: httpx.AsyncClient,
    endpoint: str,
    spec: dict[str, str],
) -> tuple[dict[str, str], dict[str, Any]]:
    response = await client.get(endpoint, params={"query": spec["metric"]})
    response.raise_for_status()
    timestamp, value = _parse_vector(response.json())
    metric = {
        "available": value is not None,
        "value": value,
        "unit": spec["unit"],
        "signal_type": spec["signal_type"],
        "source_metric": spec["metric"],
        "observed_at": (
            datetime.fromtimestamp(timestamp, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
            if timestamp is not None
            else None
        ),
    }
    return spec, metric


async def _fetch_uncached(settings: dict[str, Any]) -> dict[str, Any]:
    endpoint = f"{settings['url']}/api/v1/query"
    timeout = httpx.Timeout(float(settings["timeout"]))
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={
            "Accept": "application/json",
            "User-Agent": "fastapi-sample-core-metrics/1",
        },
    ) as client:
        results = await asyncio.gather(
            *(_query_metric(client, endpoint, spec) for spec in _METRIC_SPECS),
            return_exceptions=True,
        )

    components: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    success_count = 0
    for spec, result in zip(_METRIC_SPECS, results, strict=True):
        if isinstance(result, BaseException):
            failed.append(spec["metric"])
            continue
        resolved_spec, metric = result
        component = components.setdefault(resolved_spec["component"], {"metrics": {}})
        component["metrics"][resolved_spec["key"]] = metric
        success_count += 1

    return {
        "schema_version": 1,
        "configured": True,
        "reachable": success_count > 0,
        "complete": success_count == len(_METRIC_SPECS),
        "stale": False,
        "source": "mimir",
        "generated_at": _utc_now(),
        "components": components,
        "failed_metrics": failed,
    }


async def fetch_core_metrics_snapshot() -> dict[str, Any]:
    """Return the fixed sanitized metric projection with a short process cache."""
    global _cached_at, _cached_snapshot, _cached_url

    settings = _settings()
    if not settings["enabled"]:
        return _disabled_snapshot()
    if not settings["url"]:
        return _disabled_snapshot(invalid_url=bool(settings.get("invalid_url")))

    now = time.monotonic()
    async with _cache_lock:
        if (
            _cached_snapshot is not None
            and _cached_url == settings["url"]
            and now - _cached_at < float(settings["ttl"])
        ):
            cached = deepcopy(_cached_snapshot)
            cached["cache_age_seconds"] = round(now - _cached_at, 3)
            return cached

        try:
            snapshot = await _fetch_uncached(settings)
        except (httpx.HTTPError, ValueError, TypeError):
            if _cached_snapshot is None or _cached_url != settings["url"]:
                return {
                    "schema_version": 1,
                    "configured": True,
                    "reachable": False,
                    "complete": False,
                    "stale": False,
                    "source": "mimir",
                    "generated_at": _utc_now(),
                    "components": {},
                    "error_kind": "metrics_query_failed",
                }
            stale = deepcopy(_cached_snapshot)
            stale.update(
                {
                    "reachable": False,
                    "complete": False,
                    "stale": True,
                    "cache_age_seconds": round(now - _cached_at, 3),
                    "error_kind": "metrics_query_failed",
                }
            )
            return stale

        _cached_snapshot = snapshot
        _cached_at = time.monotonic()
        _cached_url = str(settings["url"])
        return deepcopy(snapshot)


async def reset_core_metrics_cache() -> None:
    """Reset process-local cache for deterministic tests."""
    global _cached_at, _cached_snapshot, _cached_url
    async with _cache_lock:
        _cached_snapshot = None
        _cached_at = 0.0
        _cached_url = ""
