"""Bounded Prometheus telemetry for the standalone topology view.

The topology renderer may use this data to scale nodes by observed CPU/RAM and
surface network throughput. Missing telemetry is a visualization blind spot;
it is never promoted to service downtime.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any

import httpx

from nabla.api.platform_health_diagnostics import utc_now as _utc_now
from nabla.api.prometheus_query import query_vector, sample_value
from nabla.api.truenas_app_stats import fetch_app_stats
from nabla.settings.observability import HomelabPrometheusSettings

_CACHE_TTL_SECONDS = 15.0
_cache_lock = asyncio.Lock()


@dataclass
class _TopologyTelemetryCache:
    """Mutable cache state without module-level global rebinding."""

    value: dict[str, Any] | None = None
    stored_at: float = 0.0


_cache = _TopologyTelemetryCache()

_SERVICE_LABEL = "container_label_com_docker_compose_service"
# AGENTS.md convention: the ZFS dataset /mnt/cpool/<service> belongs to catalog service <service>.
_ZFS_SERVICE_PREFIX = "/mnt/cpool/"
_ZFS_DATASETS = 'job="truenas_node",fstype="zfs",mountpoint=~"/mnt/cpool/[^/]+"'
_RESOURCE_QUERIES = {
    "cpu_cores": (
        'sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{job="truenas_cadvisor",container_label_com_docker_compose_service!=""}[2m]))'
    ),
    "memory_bytes": (
        'sum by (container_label_com_docker_compose_service) (container_memory_working_set_bytes{job="truenas_cadvisor",container_label_com_docker_compose_service!=""})'
    ),
    # This is cAdvisor filesystem usage only, not application volume/ZFS
    # dataset consumption or physical image size. Never label it as pool use.
    "fs_bytes": ('max by (container_label_com_docker_compose_service) (container_fs_usage_bytes{job="truenas_cadvisor",container_label_com_docker_compose_service!=""})'),
    "rx_bytes_per_second": (
        "sum by (container_label_com_docker_compose_service) "
        '(rate(container_network_receive_bytes_total{job="truenas_cadvisor",container_label_com_docker_compose_service!=""}[2m]))'
    ),
    "tx_bytes_per_second": (
        "sum by (container_label_com_docker_compose_service) "
        '(rate(container_network_transmit_bytes_total{job="truenas_cadvisor",container_label_com_docker_compose_service!=""}[2m]))'
    ),
    # statfs of a ZFS dataset: size - avail is the bytes it references, without child datasets or snapshots.
    "zfs_dataset_bytes": f"node_filesystem_size_bytes{{{_ZFS_DATASETS}}} - node_filesystem_avail_bytes{{{_ZFS_DATASETS}}}",
}
# Converts app.stats host CPU % into cores: the observer key may not read system.info (EACCES).
_HOST_CORES_QUERY = 'count(node_cpu_seconds_total{job="truenas_node",mode="idle"})'
_FLOW_QUERY = (
    "nabla:network_flow:pfsense_bytes_per_second or nabla:network_flow:pfsense_packets_per_second or nabla:telemetry:akvorado_inlet_up or nabla:telemetry:akvorado_outlet_up"
)


def _sample_service(field: str, labels: dict[str, Any]) -> str:
    if field != "zfs_dataset_bytes":
        return str(labels.get(_SERVICE_LABEL) or "").strip()
    mountpoint = str(labels.get("mountpoint") or "")
    name = mountpoint.removeprefix(_ZFS_SERVICE_PREFIX)
    return name if mountpoint.startswith(_ZFS_SERVICE_PREFIX) and name and "/" not in name else ""


def _resource_values(
    query_results: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, float]]:
    resources: dict[str, dict[str, float]] = {}
    for field, samples in query_results.items():
        for sample in samples:
            labels = sample.get("metric")
            if not isinstance(labels, dict):
                continue
            service = _sample_service(field, labels)
            value = sample_value(sample)
            if not service or value is None:
                continue
            resources.setdefault(service, {})[field] = round(max(0.0, value), 6)
    for _service, values in resources.items():
        # Missing one direction is not a measured zero.
        rx = values.get("rx_bytes_per_second")
        tx = values.get("tx_bytes_per_second")
        if rx is not None and tx is not None:
            values["network_bytes_per_second"] = round(rx + tx, 6)
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
        value = sample_value(sample)
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
        tasks = {field: asyncio.create_task(query_vector(query_client, expression)) for field, expression in _RESOURCE_QUERIES.items()}
        flow_task = asyncio.create_task(query_vector(query_client, _FLOW_QUERY))
        cores_task = asyncio.create_task(query_vector(query_client, _HOST_CORES_QUERY))
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
        try:
            cores_samples = await cores_task
        except (httpx.HTTPError, ValueError):
            cores_samples = []
    finally:
        if owns_client:
            await query_client.aclose()

    resources = _resource_values(results)
    cores = sample_value(cores_samples[0]) if cores_samples else None
    host_cpu_cores = int(cores) if cores is not None and cores >= 1 and cores.is_integer() else None
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
        "storage_source": "truenas_node_filesystem",
        "flow_source": "pfsense_pflow_ipfix_via_akvorado",
        "resources": resources,
        "network_flow": flow,
        "edge_bandwidth": {},
        "edge_bandwidth_state": "unattributed",
        "edge_bandwidth_detail": ("Akvorado confirms aggregate pfSense flow throughput, but no source-to-target topology edge attribution is exported yet."),
        "host_cpu_cores": host_cpu_cores,
        "query_errors": errors,
        "signals_available": signals,
        "signals_total": total,
    }


_APP_RESOURCE_KEYS = ("cpu_cores", "memory_bytes", "rx_bytes_per_second", "tx_bytes_per_second", "network_bytes_per_second")


def _has_container_signals(resources: dict[str, Any]) -> bool:
    return any(isinstance(row, dict) and (row.get("cpu_cores") is not None or row.get("memory_bytes") is not None) for row in resources.values())


async def _with_app_stats(value: dict[str, Any]) -> dict[str, Any]:
    """F07: without cAdvisor series, use TrueNAS per-App stats (App granularity, ZFS rows kept)."""
    stats = await fetch_app_stats()
    cores = value.get("host_cpu_cores")
    running = {}
    for name, row in stats.get("apps", {}).items():
        if not row.get("running"):
            continue
        projected = {key: row.get(key) for key in _APP_RESOURCE_KEYS}
        percent = row.get("cpu_host_percent")
        if projected["cpu_cores"] is None and isinstance(percent, (int, float)) and isinstance(cores, int):
            projected["cpu_cores"] = round(percent / 100 * cores, 4)
        running[name] = projected
    if stats.get("state") != "observed" or not running:
        return {**value, "app_stats_state": stats.get("state")}
    resources = dict(value.get("resources") or {})
    for name, row in running.items():
        resources[name] = {**resources.get(name, {}), **row}
    return {
        **value,
        "resources": resources,
        "resource_source": "truenas_app_stats",
        "resource_granularity": "truenas_app",
        # Prometheus signals may all be empty; the per-App sample is still a partial view.
        "state": "partial" if value.get("state") == "telemetry_unavailable" else value.get("state"),
        "app_stats_state": "observed",
        "app_stats_observed_at": stats.get("observed_at"),
    }


async def fetch_topology_telemetry(
    *,
    settings: HomelabPrometheusSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return cached topology telemetry without turning blind spots into outages."""
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
    if client is None and _cache.value is not None and now - _cache.stored_at < _CACHE_TTL_SECONDS:
        return {**_cache.value, "cached": True, "cache_age_seconds": round(now - _cache.stored_at, 3)}

    async with _cache_lock:
        now = time.monotonic()
        if client is None and _cache.value is not None and now - _cache.stored_at < _CACHE_TTL_SECONDS:
            return {**_cache.value, "cached": True, "cache_age_seconds": round(now - _cache.stored_at, 3)}
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
        # Injected Prometheus clients are tests: keep them hermetic, no TrueNAS call.
        if client is None and not _has_container_signals(value.get("resources") or {}):
            value = await _with_app_stats(value)
        if client is None:
            _cache.value = value
            _cache.stored_at = time.monotonic()
        return {**value, "cached": False, "cache_age_seconds": 0.0}
