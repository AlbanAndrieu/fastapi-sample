"""Bounded Prometheus aggregation for homelab core/telemetry overview."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import math
import re
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
_OPTIONAL_METRICS = {
    "postgres_exporter_up": "nabla:telemetry:postgres_exporter_up",
    "redis_exporter_up": "nabla:telemetry:redis_exporter_up",
    "fastapi_sample_up": "nabla:telemetry:fastapi_sample_up",
    "pyroscope_up": "nabla:telemetry:pyroscope_up",
    "alertmanager_up": "nabla:telemetry:alertmanager_up",
    "postgres_up": "nabla:service:postgres_up",
    "redis_up": "nabla:service:redis_up",
    "pfsense_memory_available_ratio": "nabla:core:pfsense_memory_available_ratio",
}
_METRIC_TO_KEY = {metric: key for key, metric in {**_METRICS, **_OPTIONAL_METRICS}.items()}
_EXPORTER_JOBS = frozenset(
    {
        "gatus",
        "fastapi_sample",
        "postgres_exporter",
        "redis_exporter",
        "pfsense_exporter",
        "crowdsec",
        "cloudflare_exporter",
        "truenas_node",
        "kafka_exporter",
        "clickhouse",
        "opensearch",
        "opensearch-security",
        "grafana",
        "alloy",
        "loki",
        "mimir",
        "tempo",
        "alertmanager",
        "pyroscope",
        "keycloak",
        "pihole_exporter",
        "haproxy",
        "n8n",
        "docling",
    },
)
_EXPORTER_RECORD = "nabla:telemetry:service_exporter_up"
_SERVICE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
_MAX_SYNTHETIC_SERVICES = 256
_SYNTHETIC_METRICS = {
    "gatus_up": "nabla:telemetry:gatus_up",
    "success": "nabla:service:synthetic_probe_success",
    "duration_seconds": "nabla:service:synthetic_probe_duration_seconds",
    "availability_ratio_5m": "nabla:service:synthetic_availability_ratio_5m",
}
_SYNTHETIC_METRIC_TO_FIELD = {metric: field for field, metric in _SYNTHETIC_METRICS.items()}
_FIXED_QUERY = " or ".join(
    (*_METRICS.values(), *_OPTIONAL_METRICS.values(), _EXPORTER_RECORD, *_SYNTHETIC_METRICS.values(), 'up{job="gatus"}'),
)
_UP_SIGNALS = (
    "truenas_node_up",
    "truenas_cadvisor_up",
    "pfsense_metrics_up",
    "prometheus_up",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _merge_binary(previous: float | None, value: float) -> float | None:
    """Fail closed on duplicate binary series; ignore non-binary samples."""
    if value not in (0.0, 1.0):
        return previous
    return value if previous is None else min(previous, value)


def _record_exporter_job(
    exporter_jobs: dict[str, float],
    labels: dict[str, Any],
    value: float,
) -> None:
    job = labels.get("job")
    if isinstance(job, str) and job in _EXPORTER_JOBS and value in (0.0, 1.0):
        # Fail closed on conflicting/duplicate series for the same job.
        previous = exporter_jobs.get(job)
        exporter_jobs[job] = value if previous is None else min(previous, value)


def _valid_synthetic_measurement(
    field: str | None,
    service_id: Any,
    probe_type: Any,
    value: float,
) -> bool:
    if field is None or not isinstance(service_id, str) or _SERVICE_ID_PATTERN.fullmatch(service_id) is None or not isinstance(probe_type, str):
        return False
    if probe_type not in {"TCP", "HTTP", "HTTPS"}:
        return False
    if field in {"success", "availability_ratio_5m"} and not 0.0 <= value <= 1.0:
        return False
    return not (field == "duration_seconds" and value < 0.0)


def _record_synthetic_sample(
    synthetic: dict[str, Any],
    labels: dict[str, Any],
    metric: str,
    value: float,
) -> None:
    field = _SYNTHETIC_METRIC_TO_FIELD.get(metric)
    if field == "gatus_up":
        synthetic["gatus_up"] = _merge_binary(synthetic["gatus_up"], value)
        return
    service_id = labels.get("nabla_service_id")
    probe_type = labels.get("type")
    if not _valid_synthetic_measurement(field, service_id, probe_type, value):
        return
    if service_id not in synthetic["services"] and len(synthetic["services"]) >= _MAX_SYNTHETIC_SERVICES:
        synthetic["truncated"] = True
        return
    service = synthetic["services"].setdefault(service_id, {})
    measurements = service.setdefault(probe_type, {})
    previous = measurements.get(field)
    measurements[field] = value if previous is None else (max(previous, value) if field == "duration_seconds" else min(previous, value))


async def _query_fixed_metrics(
    client: httpx.AsyncClient,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    values = dict.fromkeys({**_METRICS, **_OPTIONAL_METRICS})
    synthetic: dict[str, Any] = {"gatus_up": None, "services": {}}
    raw_gatus_up: float | None = None
    exporter_jobs: dict[str, float] = {}
    for sample in await query_vector(client, _FIXED_QUERY):
        labels = sample.get("metric")
        if not isinstance(labels, dict):
            continue
        metric = str(labels.get("__name__", ""))
        value = sample_value(sample)
        if value is None:
            continue
        key = _METRIC_TO_KEY.get(metric)
        if metric == _EXPORTER_RECORD:
            _record_exporter_job(exporter_jobs, labels, value)
        elif key is not None:
            values[key] = value
        elif metric == "up" and labels.get("job") == "gatus":
            raw_gatus_up = _merge_binary(raw_gatus_up, value)
        else:
            _record_synthetic_sample(synthetic, labels, metric, value)
    if synthetic["gatus_up"] is None and raw_gatus_up is not None:
        synthetic["gatus_up"] = raw_gatus_up if raw_gatus_up in (0.0, 1.0) else None
        synthetic["gatus_source"] = "raw_prometheus_up"
    synthetic["exporter_jobs"] = exporter_jobs
    return values, synthetic


def _synthetic_summary(
    synthetic: dict[str, Any] | None = None,
    *,
    state: str | None = None,
) -> dict[str, Any]:
    payload = synthetic or {}
    services = payload.get("services")
    gatus_up = payload.get("gatus_up")
    return {
        "source": "gatus_via_prometheus",
        "shadow_only": True,
        "state": state
        or ("observed" if isinstance(gatus_up, float) and math.isfinite(gatus_up) and gatus_up == 1.0 and payload.get("truncated") is not True else "telemetry_unavailable"),
        "gatus_up": gatus_up,
        "gatus_source": payload.get("gatus_source", "recording_rule" if gatus_up is not None else "unavailable"),
        "service_count": len(services) if isinstance(services, dict) else 0,
        "truncated": payload.get("truncated") is True,
        "services": services if isinstance(services, dict) else {},
    }


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
        "optional_exporters": {name: values.get(name) for name in _OPTIONAL_METRICS},
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
            "synthetic_probes": _synthetic_summary(state="not_configured"),
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
        values, synthetic = await _query_fixed_metrics(query_client)
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
            "synthetic_probes": _synthetic_summary(state="telemetry_unavailable"),
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
        "synthetic_probes": _synthetic_summary(synthetic),
        "exporter_jobs": synthetic.get("exporter_jobs", {}),
        "metrics": {
            key: {
                "metric": metric,
                "value": round(value, 6) if (value := values.get(key)) is not None else None,
            }
            # Optional exporters are reported in summary.optional_exporters only.
            for key, metric in _METRICS.items()
        },
        "summary": _summary(values),
    }
