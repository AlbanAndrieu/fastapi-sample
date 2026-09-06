"""Bounded Prometheus aggregation for homelab core/telemetry overview."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from typing import Any

import httpx

from nabla.settings.observability import HomelabPrometheusSettings

logger = logging.getLogger(__name__)

_METRICS = {
    "truenas_memory_available_ratio": "nabla:core:truenas_memory_available_ratio",
    "truenas_cpu_busy_ratio": "nabla:core:truenas_cpu_busy_ratio",
    "truenas_node_up": "nabla:telemetry:truenas_node_up",
    "truenas_cadvisor_up": "nabla:telemetry:truenas_cadvisor_up",
    "pfsense_metrics_up": "nabla:telemetry:pfsense_metrics_up",
    "prometheus_up": "nabla:observability:prometheus_up",
}
_UP_SIGNALS = (
    "truenas_node_up",
    "truenas_cadvisor_up",
    "pfsense_metrics_up",
    "prometheus_up",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _vector_value(payload: dict[str, Any]) -> float | None:
    if payload.get("status") != "success":
        return None
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        return None
    result = data.get("result")
    if not isinstance(result, list) or len(result) != 1:
        return None
    sample = result[0]
    if not isinstance(sample, dict):
        return None
    value = sample.get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return _safe_float(value[1])


async def _query_metric(
    client: httpx.AsyncClient,
    metric: str,
) -> float | None:
    response = await client.get(
        "/api/v1/query",
        params={"query": metric},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    return _vector_value(payload)


def _summary(values: dict[str, float | None]) -> dict[str, Any]:
    available = sum(values.get(name) is not None for name in _METRICS)
    up = sum((values.get(name) or 0.0) >= 1.0 for name in _UP_SIGNALS)
    return {
        "signals_available": available,
        "signals_total": len(_METRICS),
        "telemetry_up": up,
        "telemetry_total": len(_UP_SIGNALS),
        "truenas_memory_available_ratio": values.get(
            "truenas_memory_available_ratio"
        ),
        "truenas_cpu_busy_ratio": values.get("truenas_cpu_busy_ratio"),
        "pfsense_metrics_up": values.get("pfsense_metrics_up"),
    }


def _state(values: dict[str, float | None]) -> str:
    if any(values.get(name) is None for name in _METRICS):
        return "degraded"
    if any((values.get(name) or 0.0) < 1.0 for name in _UP_SIGNALS):
        return "degraded"
    return "healthy"


async def fetch_platform_metrics(
    *,
    settings: HomelabPrometheusSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Read only the fixed recording-rule contract from trusted Prometheus."""

    effective = settings or HomelabPrometheusSettings()
    if not effective.configured:
        return {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "state": "not_configured",
            "configured": False,
            "source": "prometheus",
            "metrics": {},
            "summary": {
                "signals_available": 0,
                "signals_total": len(_METRICS),
                "telemetry_up": 0,
                "telemetry_total": len(_UP_SIGNALS),
            },
        }

    owns_client = client is None
    timeout = httpx.Timeout(effective.homelab_prometheus_timeout_seconds)
    query_client = client or httpx.AsyncClient(
        base_url=effective.base_url,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )

    try:
        results = await asyncio.gather(
            *(_query_metric(query_client, metric) for metric in _METRICS.values())
        )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "homelab prometheus query failed exception_type=%s",
            type(exc).__name__,
        )
        return {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "state": "telemetry_unavailable",
            "configured": True,
            "source": "prometheus",
            "error_kind": "query_failed",
            "exception_type": type(exc).__name__,
            "metrics": {},
            "summary": {
                "signals_available": 0,
                "signals_total": len(_METRICS),
                "telemetry_up": 0,
                "telemetry_total": len(_UP_SIGNALS),
            },
        }
    finally:
        if owns_client:
            await query_client.aclose()

    values = dict(zip(_METRICS, results, strict=True))
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "state": _state(values),
        "configured": True,
        "source": "prometheus",
        "metrics": {
            key: {
                "metric": _METRICS[key],
                "value": round(value, 6) if value is not None else None,
            }
            for key, value in values.items()
        },
        "summary": _summary(values),
    }
