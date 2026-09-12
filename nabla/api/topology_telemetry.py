"""Bounded Prometheus telemetry for the standalone topology view.

The topology renderer may use this data to scale nodes by observed CPU/RAM and
surface network throughput. Missing telemetry is a visualization blind spot;
it is never promoted to service downtime.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import math
import time
from typing import Any

import httpx

from nabla.settings.observability import HomelabPrometheusSettings

_CACHE_TTL_SECONDS = 15.0
_cache_lock = asyncio.Lock()
_cache_value: dict[str, Any] | None = None
_cache_stored_at = 0.0

_SERVICE_LABEL = "container_label_com_docker_compose_service"
_RESOURCE_QUERIES = {
    "cpu_cores": (
        "sum by (container_label_com_docker_compose_service) "
        "(rate(container_cpu_usage_seconds_total{job=\"truenas_cadvisor\","
        "container_label_com_docker_compose_service!=\"\"}[2m]))"
    ),
    "memory_bytes": (
        "sum by (container_label_com_docker_compose_service) "
        "(container_memory_working_set_bytes{job=\"truenas_cadvisor\","
        "container_label_com_docker_compose_service!=\"\"})"
    ),
    "rx_bytes_per_second": (
        "sum by (container_label_com_docker_compose_service) "
        "(rate(container_network_receive_bytes_total{job=\"truenas_cadvisor\","
        "container_label_com_docker_compose_service!=\"\"}[2m]))"
    ),
    "tx_bytes_per_second": (
        "sum by (container_label_com_docker_compose_service) "
        "(rate(container_network_transmit_bytes_total{job=\"truenas_cadvisor\","
        "container_label_com_docker_compose_service!=\"\"}[2m]))"
    ),
}
_FLOW_QUERY = (
    "nabla:network_flow:pfsense_bytes_per_second or "
    "nabla:network_flow:pfsense_packets_per_second or "
    "nabla:telemetry:akvorado_inlet_up or "
    "nabla:telemetry:akvorado_outlet_up"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _vector(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("resultType") != "vector":
        return []
    result = data.get("result")
    return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []


def _sample_value(sample: dict[str, Any]) -> float | None:
    raw = sample.get("value")
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    return _safe_float(raw[1])


async def _query(client: httpx.AsyncClient, expression: str) -> list[dict[str, Any]]:
    response = await client.get(
        "/api/v1/query",
        params={"query": expression},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    return _vector(response.json())


def _resource_values(
    query_results: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, float]]:
    resources: dict[str, dict[str, float]] = {}
    for field, samples in query_results.items():
        for sample in samples:
            labels = sample.get("metric")
            if not isinstance(labels, dict):
                continue
            service = str(labels.get(_SERVICE_LABEL) or "").strip()
            value = _sample_value(sample)
            if not service or value is None:
                continue
            resources.setdefault(service, {})[field] = round(max(0.0, value), 6)
    for service, values in resources.items():
        values["network_bytes_per_second"] = round(
            values.get("rx_bytes_per_second", 0.0)
            + values.get("tx_bytes_per_second", 0.0),
            6,
        )
    return resources


def _flow_values(samples: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "pfsense_bytes_per_second": None,
        "pfsense_packets_per_second": None,
        "akvorado_inlet_up": None,
        "akvorado_outlet_up": None,
    }
    names = {
        "nabla:network_flow:pfsense_bytes_per_second": "pfsense_bytes_per_second",
        "nabla:network_flow:pfsense_packets_per_second": "pfsense_packets_per_second",
        "nabla:telemetry:akvorado_inlet_up": "akvorado_inlet_up",
        "nabla:telemetry:akvorado_outlet_up": "akvorado_outlet_up",
    }
    for sample in samples:
        labels = sample.get("metric")
        if not isinstance(labels, dict):
            continue
        key = names.get(str(labels.get("__name__") or ""))
        value = _sample_value(sample)
        if key is not None and value is not None:
            out[key] = round(max(0.0, value), 6)
    return out


async def _fetch_origin(
    settings: HomelabPrometheusSettings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    query_client = client or httpx.AsyncClient(
        base_url=settings.base_url,
        timeout=httpx.Timeout(settings.homelab_prometheus_timeout_seconds),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        tasks = {
            field: asyncio.create_task(_query(query_client, expression))
            for field, expression in _RESOURCE_QUERIES.items()
        }
        flow_task = asyncio.create_task(_query(query_client, _FLOW_QUERY))
        results: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for field, task in tasks.items():
            try:
                results[field] = await task
            except (httpx.HTTPError, ValueError) as exc:
                errors[field] = type(exc).__name__
                results[field] = []
        try:
            flow_samples = await flow_task
        except (httpx.HTTPError, ValueError) as exc:
            errors["network_flow"] = type(exc).__name__
            flow_samples = []
    finally:
        if owns_client:
            await query_client.aclose()

    resources = _resource_values(results)
    flow = _flow_values(flow_samples)
    signals = sum(bool(values) for values in results.values()) + int(bool(flow_samples))
    total = len(_RESOURCE_QUERIES) + 1
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "state": "healthy" if signals == total else "partial" if signals else "telemetry_unavailable",
        "configured": True,
        "source": "prometheus",
        "resource_source": "truenas_cadvisor",
        "flow_source": "pfsense_pflow_ipfix_via_akvorado",
        "resources": resources,
        "network_flow": flow,
        "edge_bandwidth": {},
        "edge_bandwidth_state": "unattributed",
        "edge_bandwidth_detail": (
            "Akvorado confirms aggregate pfSense flow throughput, but no source-to-target topology edge attribution is exported yet."
        ),
        "query_errors": errors,
        "signals_available": signals,
        "signals_total": total,
    }


async def fetch_topology_telemetry(
    *,
    settings: HomelabPrometheusSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return cached topology telemetry without turning blind spots into outages."""
    global _cache_stored_at, _cache_value

    effective = settings or HomelabPrometheusSettings()
    if not effective.configured:
        return {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "state": "not_configured",
            "configured": False,
            "source": "prometheus",
            "resource_source": "truenas_cadvisor",
            "flow_source": "pfsense_pflow_ipfix_via_akvorado",
            "resources": {},
            "network_flow": {},
            "edge_bandwidth": {},
            "edge_bandwidth_state": "unavailable",
            "edge_bandwidth_detail": "Prometheus telemetry is not configured for this runtime.",
        }

    now = time.monotonic()
    if client is None and _cache_value is not None and now - _cache_stored_at < _CACHE_TTL_SECONDS:
        return {**_cache_value, "cached": True, "cache_age_seconds": round(now - _cache_stored_at, 3)}

    async with _cache_lock:
        now = time.monotonic()
        if client is None and _cache_value is not None and now - _cache_stored_at < _CACHE_TTL_SECONDS:
            return {**_cache_value, "cached": True, "cache_age_seconds": round(now - _cache_stored_at, 3)}
        try:
            value = await _fetch_origin(effective, client)
        except (httpx.HTTPError, ValueError) as exc:
            value = {
                "schema_version": 1,
                "generated_at": _utc_now(),
                "state": "telemetry_unavailable",
                "configured": True,
                "source": "prometheus",
                "resource_source": "truenas_cadvisor",
                "flow_source": "pfsense_pflow_ipfix_via_akvorado",
                "resources": {},
                "network_flow": {},
                "edge_bandwidth": {},
                "edge_bandwidth_state": "unavailable",
                "edge_bandwidth_detail": "Topology telemetry query failed; declared topology remains authoritative.",
                "error_kind": "query_failed",
                "exception_type": type(exc).__name__,
            }
        if client is None:
            _cache_value = value
            _cache_stored_at = time.monotonic()
        return {**value, "cached": False, "cache_age_seconds": 0.0}
