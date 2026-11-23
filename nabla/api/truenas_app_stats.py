"""F07: per-App resources from the TrueNAS ``app.stats`` event source.

Compose disabled cAdvisor, so ``container_*`` series are gone. ``app.stats`` is
the only per-App source TrueNAS serves (role APPS_READ on the existing read-only
observer key). Rows are per TrueNAS App, not per Compose service. A sample costs
one ~2 s subscription on the NAS: it is cached and never runs on the event loop.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import math
import threading
import time
from typing import Any

from nabla.api.platform_health_diagnostics import utc_now
from nabla.api.truenas_client import build_truenas_adapter
from nabla.integrations.truenas_client import TrueNASHealthProbeError

SOURCE = "truenas_app_stats"
GRANULARITY = "truenas_app"
CALL_TIMEOUT_SECONDS = 3.0
# The event source sleeps its default 2 s interval before the first sample.
FIRST_EVENT_SECONDS = 6.0
DEADLINE_SECONDS = 10.0
_CACHE_SECONDS = 30.0
_MAX_APPS = 200
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


def _non_negative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _rate_sum(networks: list[dict[str, Any]], key: str) -> float | None:
    values = [_non_negative(network.get(key)) for network in networks]
    return sum(values) if values and all(value is not None for value in values) else None  # type: ignore[arg-type]


def project_app_stats(rows: object, cores: object) -> dict[str, dict[str, Any]]:
    """Map ``app.stats`` rows onto the topology resource keys.

    ``cpu_usage`` is a percentage of the whole host (middleware divides by the
    core count), so ``cpu_cores`` needs ``system.info`` cores. The middleware
    pads stopped Apps with zeros: they become ``running: False`` without values,
    so the heatmap shows an absence, never a measured 0.
    """
    core_count = cores if isinstance(cores, int) and not isinstance(cores, bool) and cores > 0 else None
    apps: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if len(apps) >= _MAX_APPS:
            break
        if not isinstance(row, dict):
            continue
        name = row.get("app_name")
        if not isinstance(name, str) or not 0 < len(name) <= 64 or name in apps:
            continue
        networks = [network for network in row.get("networks") or [] if isinstance(network, dict)]
        memory = _non_negative(row.get("memory"))
        if not networks and not memory:
            apps[name] = {"running": False}
            continue
        cpu_percent = _non_negative(row.get("cpu_usage"))
        rx, tx = _rate_sum(networks, "rx_bytes"), _rate_sum(networks, "tx_bytes")
        blkio = row.get("blkio") if isinstance(row.get("blkio"), dict) else {}
        apps[name] = {
            "running": True,
            "cpu_host_percent": round(cpu_percent, 3) if cpu_percent is not None else None,
            "cpu_cores": round(cpu_percent / 100 * core_count, 4) if cpu_percent is not None and core_count else None,
            "memory_bytes": memory,
            "rx_bytes_per_second": rx,
            "tx_bytes_per_second": tx,
            "network_bytes_per_second": rx + tx if rx is not None and tx is not None else None,
            # Cumulative container counters, not a rate.
            "blkio_read_bytes_total": _non_negative(blkio.get("read")),
            "blkio_write_bytes_total": _non_negative(blkio.get("write")),
        }
    return apps


def collect_app_stats(adapter: Any) -> dict[str, Any]:
    """Take one ``app.stats`` sample through the adapter; blocking, run in a thread."""
    samples: list[object] = []
    ready = threading.Event()

    def on_event(_message_type: str, **params: Any) -> None:
        if not ready.is_set() and isinstance(params.get("fields"), list):
            samples.append(params["fields"])
            ready.set()

    with adapter.read_only_session(call_timeout=CALL_TIMEOUT_SECONDS) as client:
        try:
            info = client.call("system.info")
        except Exception:  # Cores only convert CPU %; the sample stays usable without them.
            info = None
        subscription = client.subscribe("app.stats", on_event)
        try:
            received = ready.wait(FIRST_EVENT_SECONDS)
        finally:
            client.unsubscribe(subscription)
    if not received:
        return {"state": "telemetry_unavailable", "reason": "no_event"}
    cores = info.get("cores") if isinstance(info, dict) else None
    apps = project_app_stats(samples[0], cores)
    return {"state": "observed", "cores": cores if isinstance(cores, int) else None, "apps": apps}


def _base(observed_at: str) -> dict[str, Any]:
    return {"schema_version": 1, "source": SOURCE, "granularity": GRANULARITY, "observed_at": observed_at}


async def fetch_app_stats(*, adapter: Any | None = None, use_cache: bool = True) -> dict[str, Any]:
    """Return the cached per-App sample (30 s) or take a new one under a deadline."""
    observed_at = utc_now()
    effective = adapter if adapter is not None else build_truenas_adapter()
    if effective is None:
        return {**_base(observed_at), "state": "not_configured", "reason": "truenas_credentials_missing", "apps": {}}
    hit = _CACHE.get("apps") if use_cache else None
    if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return {**deepcopy(hit[1]), "cached": True}
    async with _CACHE_LOCK:
        hit = _CACHE.get("apps") if use_cache else None
        if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
            return {**deepcopy(hit[1]), "cached": True}
        try:
            collected = await asyncio.wait_for(asyncio.to_thread(collect_app_stats, effective), timeout=DEADLINE_SECONDS)
            payload = {**_base(observed_at), "apps": {}, **collected}
        except TimeoutError:
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": "timeout", "apps": {}}
        except TrueNASHealthProbeError as exc:
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": exc.stage, "apps": {}}
        except Exception as exc:  # Transport or permission errors are evidence, never a 500.
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": exc.__class__.__name__, "apps": {}}
        if use_cache:
            _CACHE["apps"] = (time.monotonic(), deepcopy(payload))
        return {**payload, "cached": False}


def reset_app_stats_cache() -> None:
    _CACHE.clear()
