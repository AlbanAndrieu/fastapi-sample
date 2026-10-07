"""Bounded Prometheus aggregation for homelab core/telemetry overview."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

import httpx

from nabla.api.prometheus_query import query_vector, sample_value
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
_METRIC_TO_KEY = {metric: key for key, metric in _METRICS.items()}
_FIXED_QUERY = " or ".join(_METRICS.values())
_UP_SIGNALS = (
    "truenas_node_up",
    "truenas_cadvisor_up",
    "pfsense_metrics_up",
    "prometheus_up",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def _query_fixed_metrics(client: httpx.AsyncClient) -> dict[str, float | None]:
    values = dict.fromkeys(_METRICS)
    for sample in await query_vector(client, _FIXED_QUERY):
        metric_labels = sample.get("metric")
        if not isinstance(metric_labels, dict):
            continue
        key = _METRIC_TO_KEY.get(str(metric_labels.get("__name__", "")))
        value = sample_value(sample)
        if key is not None and value is not None:
            values[key] = value
    return values


def _summary(values: dict[str, float | None]) -> dict[str, Any]:
    available = sum(values.get(name) is not None for name in _METRICS)
    up = sum((values.get(name) or 0.0) >= 1.0 for name in _UP_SIGNALS)
    return {
        "signals_available": available,
        "signals_total": len(_METRICS),
        "telemetry_up": up,
        "telemetry_total": len(_UP_SIGNALS),
        "truenas_memory_available_ratio": values.get(
            "truenas_memory_available_ratio",
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
        values = await _query_fixed_metrics(query_client)
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
