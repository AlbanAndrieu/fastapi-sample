"""Read-only, bounded Prometheus history for the OWNER operations screen.

No raw PromQL, arbitrary target, service label, or range enters via HTTP.
The browser only receives fixed-length timestamp/value pairs without labels.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import time
from typing import Any

import httpx

from nabla.api.prometheus_query import query_matrix_range
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.settings.observability import HomelabPrometheusSettings

# Each window is bounded to 337 samples per series.
WINDOWS: dict[str, tuple[int, int]] = {
    "1h": (3600, 60),
    "24h": (86400, 300),
    "7d": (604800, 1800),
}
_DEFAULT_WINDOW = "1h"
_MAX_SAMPLES = 350
_CACHE_SECONDS = 120.0
_OVERALL_DEADLINE_SECONDS = 9.0
_SERVICE_MATCH = "sample|fastapi-sample|fastapi_sample|albandrieu_sample"
_CADVISOR = 'job="truenas_cadvisor",container_label_com_docker_compose_service=~"' + _SERVICE_MATCH + '"'
_FIXED_QUERIES = {
    "cpu_cores": (
        "sum by (container_label_com_docker_compose_service) "
        f"(rate(container_cpu_usage_seconds_total{{{_CADVISOR}}}[5m]))"
    ),
    "memory_bytes": (
        "sum by (container_label_com_docker_compose_service) "
        f"(container_memory_working_set_bytes{{{_CADVISOR}}})"
    ),
    "network_bytes_per_second": (
        "sum by (container_label_com_docker_compose_service) "
        f"(rate(container_network_receive_bytes_total{{{_CADVISOR}}}[5m])) + "
        "sum by (container_label_com_docker_compose_service) "
        f"(rate(container_network_transmit_bytes_total{{{_CADVISOR}}}[5m]))"
    ),
    # Instrumentator exports seconds; the chart explicitly shows milliseconds.
    "http_p95_ms": (
        "1000 * histogram_quantile(0.95, sum by (le) "
        '(rate(http_request_duration_seconds_bucket{job="fastapi_sample"}[5m])))'
    ),
    # Optional recording rule from Gatus / Prometheus; no missing-as-zero.
    "gatus_availability_percent": (
        '100 * nabla:service:synthetic_availability_ratio_5m{'
        'nabla_service_id=~"sample|fastapi-sample"}'
    ),
}
_UNITS = {
    "cpu_cores": "cores",
    "memory_bytes": "bytes",
    "network_bytes_per_second": "bytes/s",
    "http_p95_ms": "ms",
    "gatus_availability_percent": "%",
}
_SERVICE_SERIES = frozenset({"cpu_cores", "memory_bytes", "network_bytes_per_second"})
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


@dataclass(slots=True)
class _RequestWindow:
    end: int
    start: int
    step: int
    label: str


def _window(label: str) -> _RequestWindow:
    seconds, step = WINDOWS[label]
    end = int(time.time()) // step * step
    return _RequestWindow(
        end=end,
        start=end - seconds,
        step=step,
        label=label,
    )


def _safe_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _sanitize_matrix(
    payload: object,
    metric: str,
    window: _RequestWindow,
) -> list[list[float | int]]:
    """Drop unsafe labels, ambiguous series, out-of-window and invalid values."""
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("Prometheus query_range failed")
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "matrix":
        raise ValueError("Invalid Prometheus matrix result")
    result = data.get("result")
    if not isinstance(result, list):
        raise ValueError("Invalid Prometheus series list")
    if len(result) != 1:
        # Zero samples or ambiguous service/instance labels mean no evidence.
        return []
    series = result[0]
    if not isinstance(series, dict):
        return []
    labels = series.get("metric")
    if not isinstance(labels, dict):
        return []
    if metric in _SERVICE_SERIES:
        service = labels.get("container_label_com_docker_compose_service")
        if service not in {
            "sample", "fastapi-sample", "fastapi_sample", "albandrieu_sample"
        }:
            return []
    observations = series.get("values")
    if not isinstance(observations, list) or len(observations) > _MAX_SAMPLES:
        raise ValueError("Oversized Prometheus matrix")
    clean: dict[int, float] = {}
    ambiguous: set[int] = set()
    for pair in observations:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        timestamp = _safe_number(pair[0])
        value = _safe_number(pair[1])
        if timestamp is None or value is None:
            continue
        timestamp_int = int(timestamp)
        if not window.start <= timestamp_int <= window.end:
            continue
        if (timestamp_int - window.start) % window.step != 0:
            continue
        if metric == "gatus_availability_percent" and value > 100:
            continue
        if timestamp_int in ambiguous:
            continue
        if timestamp_int in clean:
            # Duplicate timestamps remain ambiguous even after a third row.
            del clean[timestamp_int]
            ambiguous.add(timestamp_int)
            continue
        clean[timestamp_int] = round(value, 6)
    return [[stamp, clean[stamp]] for stamp in sorted(clean)]


def _failure_kind(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {301, 302, 303, 307, 308}:
            return "access_redirect"
        if status in {401, 403}:
            return "authentication_rejected"
        if status == 429:
            return "rate_limited"
        return "http_failure"
    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connection_failed"
    if isinstance(exc, ValueError):
        return "invalid_matrix"
    return "query_unavailable"


async def _fetch_history(
    settings: HomelabPrometheusSettings,
    window: _RequestWindow,
    client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    owned = client is None
    query_client = client or httpx.AsyncClient(
        base_url=settings.base_url,
        timeout=httpx.Timeout(settings.homelab_prometheus_timeout_seconds),
        headers=settings.access_headers,
        follow_redirects=False,
        trust_env=False,
    )
    series: dict[str, list[list[float | int]]] = {}
    errors: dict[str, str] = {}
    semaphore = asyncio.Semaphore(2)

    async def collect(field: str, expression: str) -> None:
        async with semaphore:
            try:
                payload = await query_matrix_range(
                    query_client, expression,
                    start=window.start, end=window.end, step=window.step,
                )
                series[field] = _sanitize_matrix(payload, field, window)
            except (httpx.HTTPError, ValueError) as exc:
                errors[field] = _failure_kind(exc)
                series[field] = []

    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(collect(name, query) for name, query in _FIXED_QUERIES.items())
            ),
            timeout=_OVERALL_DEADLINE_SECONDS,
        )
    finally:
        if owned:
            await query_client.aclose()
    for field in _FIXED_QUERIES:
        series.setdefault(field, [])
    populated = sum(bool(values) for values in series.values())
    return {
        "schema_version": 1,
        "model": "owner-operations-history",
        "window": window.label,
        "step_seconds": window.step,
        "start": window.start,
        "end": window.end,
        "state": (
            "observed" if populated == len(series)
            else "partial" if populated
            else "telemetry_unavailable"
        ),
        "source": "prometheus_query_range",
        "units": dict(_UNITS),
        "series": series,
        "errors": errors,
        "synthetic": False,
    }


async def fetch_home_metrics_history(
    window: str = _DEFAULT_WINDOW,
    *,
    settings: HomelabPrometheusSettings | None = None,
    client: httpx.AsyncClient | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Fetch only fixed expressions, with a per-window shared L1 TTL."""
    if window not in WINDOWS:
        raise ValueError("Unsupported history window")
    spec = _window(window)
    active = homelab_runtime_detected() if enabled is None else enabled
    effective = settings or HomelabPrometheusSettings()
    base = {
        "schema_version": 1,
        "model": "owner-operations-history",
        "window": window,
        "step_seconds": spec.step,
        "start": spec.start,
        "end": spec.end,
        "source": "prometheus_query_range",
        "units": dict(_UNITS),
        "series": {key: [] for key in _FIXED_QUERIES},
        "errors": {},
        "synthetic": False,
    }
    if not active:
        return {**base, "state": "not_executed", "reason": "homelab_only"}
    if not effective.configured:
        return {**base, "state": "not_configured", "reason": "prometheus_missing"}
    if client is not None:
        try:
            return await _fetch_history(effective, spec, client)
        except TimeoutError:
            return {**base, "state": "telemetry_unavailable", "reason": "timeout"}
    key = f"{effective.base_url}|{window}"
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_SECONDS:
        return {**hit[1], "cached": True}
    async with _CACHE_LOCK:
        hit = _CACHE.get(key)
        now = time.monotonic()
        if hit and now - hit[0] < _CACHE_SECONDS:
            return {**hit[1], "cached": True}
        try:
            payload = await _fetch_history(effective, spec, None)
        except TimeoutError:
            payload = {**base, "state": "telemetry_unavailable", "reason": "timeout"}
        _CACHE[key] = (time.monotonic(), payload)
        return {**payload, "cached": False}
