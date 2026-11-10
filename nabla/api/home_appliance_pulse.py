"""Live TrueNAS appliance pulse for the OWNER operations screen.

Everything comes from documented read-only TrueNAS middleware methods
(`system.info`, `alert.list`, `pool.query`, `interface.query`, `app.query`,
`reporting.netdata_graphs`, `reporting.netdata_get_data`) through the
existing observer credential. Each call is optional: a failing call yields an
explicit per-section state, never an invented value. Impacts are derived only
from signals observed in the same snapshot and are labelled as associations.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import math
import re
import time
from typing import Any

from nabla.api.home_appliance_impacts import FAIL_LEVELS, derive_impacts, worst_state
from nabla.api.platform_health_diagnostics import utc_now
from nabla.api.truenas_client import build_truenas_adapter
from nabla.integrations.truenas_client import TrueNASHealthProbeError, _rpc_failure_stage

MODEL = "owner-appliance-pulse"
SOURCE = "truenas_middleware"
DEADLINE_SECONDS = 8.0
CALL_TIMEOUT_SECONDS = 3.0
_CACHE_SECONDS = 30.0
_MAX_SERIES_POINTS = 400
_MAX_ALERT_ITEMS = 20
_MAX_LIST = 20
_TEXT_LIMIT = 160
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


def _finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _non_negative_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _clean_text(value: object) -> str:
    text = _SPACES.sub(" ", _TAG.sub(" ", str(value or ""))).strip()
    return text[:_TEXT_LIMIT]


# ---------------------------------------------------------------------------
# Collection (synchronous, one authenticated session)
# ---------------------------------------------------------------------------
class _Session:
    """Run optional read-only calls and keep a per-method failure stage."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.errors: dict[str, str] = {}

    def optional(self, key: str, method: str, *params: Any) -> Any:
        try:
            return self._client.call(method, *params)
        except Exception as exc:  # One failing method must not hide the others.
            # Classification only: middleware error text never reaches the browser.
            self.errors[key] = f"{_rpc_failure_stage(exc)}:{exc.__class__.__name__}"
            return None


def _system_section(info: object) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {"state": "unavailable"}
    loads = []
    for item in info.get("loadavg") or []:
        number = _finite(item if not isinstance(item, dict) else item.get("value", item.get("load")))
        loads.append(number)
    cores = _non_negative_int(info.get("cores"))
    load_1m = loads[0] if loads else None
    per_core = round(load_1m / cores, 3) if load_1m is not None and cores else None
    return {
        "state": "observed",
        "version": str(info.get("version") or "")[:64] or None,
        "cores": cores,
        "physmem_bytes": _non_negative_int(info.get("physmem")),
        "uptime_seconds": _finite(info.get("uptime_seconds")),
        "load": {"1m": load_1m, "5m": loads[1] if len(loads) > 1 else None, "15m": loads[2] if len(loads) > 2 else None},
        "load_per_core_1m": per_core,
    }


def _alerts_section(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {"state": "unavailable", "total": None, "active": None, "by_level": {}, "items": []}
    by_level: dict[str, int] = {}
    items = []
    active = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        level = str(row.get("level") or "UNKNOWN").upper()[:16]
        dismissed = row.get("dismissed") is True
        if not dismissed:
            active += 1
            by_level[level] = by_level.get(level, 0) + 1
        items.append(
            {
                "klass": str(row.get("klass") or "")[:64],
                "level": level,
                "dismissed": dismissed,
                "since": str(row.get("datetime") or "")[:32] or None,
                "text": _clean_text(row.get("formatted") or row.get("text")),
            },
        )
    items.sort(key=lambda item: (item["dismissed"], item["level"] not in FAIL_LEVELS, item["klass"]))
    return {"state": "observed", "total": len(items), "active": active, "by_level": by_level, "items": items[:_MAX_ALERT_ITEMS]}


def _pools_section(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {"state": "unavailable", "pools": [], "worst_used_percent": None}
    pools = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        size = _non_negative_int(row.get("size"))
        allocated = _non_negative_int(row.get("allocated"))
        used = round(100.0 * allocated / size, 2) if size and allocated is not None else None
        fragmentation = _finite(str(row.get("fragmentation") or "").rstrip("%"))
        scan = row.get("scan") if isinstance(row.get("scan"), dict) else {}
        pools.append(
            {
                "name": str(row.get("name") or "")[:64],
                "status": str(row.get("status") or "")[:32],
                "healthy": row.get("healthy") is True,
                "warning": row.get("warning") is True,
                "size_bytes": size,
                "allocated_bytes": allocated,
                "free_bytes": _non_negative_int(row.get("free")),
                "used_percent": used,
                "fragmentation_percent": fragmentation,
                "scan": {
                    "function": str(scan.get("function") or "")[:16] or None,
                    "state": str(scan.get("state") or "")[:16] or None,
                    "percentage": _finite(scan.get("percentage")),
                },
            },
        )
    used_values = [pool["used_percent"] for pool in pools if pool["used_percent"] is not None]
    return {"state": "observed", "pools": pools[:_MAX_LIST], "worst_used_percent": max(used_values) if used_values else None}


def _interfaces_section(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {"state": "unavailable", "physical": [], "links_down": []}
    physical = []
    down = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("type") or "").upper() not in {"PHYSICAL", "LINK_AGGREGATION"}:
            continue
        name = str(row.get("name") or "")[:32]
        state = row.get("state") if isinstance(row.get("state"), dict) else {}
        link = str(state.get("link_state") or "").upper()
        up = "UP" in link
        physical.append({"name": name, "type": str(row.get("type")).upper(), "link_up": up})
        if not up:
            down.append(name)
    return {"state": "observed", "physical": physical[:_MAX_LIST], "links_down": down[:_MAX_LIST]}


def _apps_section(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {"state": "unavailable", "total": None, "counts": {}, "crashed": [], "deploying": []}
    counts: dict[str, int] = {}
    crashed = []
    deploying = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "UNKNOWN").upper()[:16]
        counts[state] = counts.get(state, 0) + 1
        app_id = str(row.get("id") or row.get("name") or "")[:64]
        if state == "CRASHED":
            crashed.append(app_id)
        elif state == "DEPLOYING":
            deploying.append(app_id)
    return {
        "state": "observed",
        "total": sum(counts.values()),
        "counts": counts,
        "crashed": sorted(crashed)[:_MAX_LIST],
        "deploying": sorted(deploying)[:_MAX_LIST],
    }


def _graph_columns(graph: object) -> tuple[list[int], dict[str, list[float | None]]] | None:
    """Return timestamps and named columns from one netdata graph, or None."""
    if not isinstance(graph, dict):
        return None
    legend = graph.get("legend")
    data = graph.get("data")
    if not isinstance(legend, list) or not legend or not isinstance(data, list) or len(data) > _MAX_SERIES_POINTS:
        return None
    names = [str(name) for name in legend]
    if names[0].lower() not in {"time", "timestamp"}:
        return None
    timestamps: list[int] = []
    columns: dict[str, list[float | None]] = {name: [] for name in names[1:]}
    previous = -1
    for row in data:
        if isinstance(row, dict):
            values = [row.get(name) for name in names]
        elif isinstance(row, list) and len(row) == len(names):
            values = row
        else:
            return None
        stamp = _finite(values[0])
        if stamp is None or int(stamp) <= previous:
            return None
        previous = int(stamp)
        timestamps.append(previous)
        for name, value in zip(names[1:], values[1:], strict=True):
            columns[name].append(_finite(value))
    return timestamps, columns


def _percent_series(timestamps: list[int], values: list[float | None]) -> list[list[float]]:
    series = []
    for stamp, value in zip(timestamps, values, strict=True):
        if value is not None and 0.0 <= value <= 100.0:
            series.append([stamp, round(value, 2)])
    return series


def _cpu_from_graph(graph: object, label: str | None) -> dict[str, Any]:
    parsed = _graph_columns(graph)
    if parsed is None:
        return {"state": "unavailable", "busy_percent": None, "series": []}
    timestamps, columns = parsed
    lowered = {name.lower(): values for name, values in columns.items()}
    if "idle" in lowered:
        busy = [None if idle is None else 100.0 - idle for idle in lowered["idle"]]
        derivation = "100_minus_idle"
    elif len(lowered) == 1:
        busy = next(iter(lowered.values()))
        derivation = "single_column_percent"
    else:
        return {"state": "legend_unrecognized", "legend": sorted(lowered)[:_MAX_LIST], "busy_percent": None, "series": []}
    series = _percent_series(timestamps, busy)
    return {
        "state": "observed" if series else "unavailable",
        "derivation": derivation,
        "vertical_label": label,
        "busy_percent": series[-1][1] if series else None,
        "series": series,
    }


def _memory_from_graph(graph: object, label: str | None) -> dict[str, Any]:
    parsed = _graph_columns(graph)
    if parsed is None:
        return {"state": "unavailable", "used_percent": None, "series": []}
    timestamps, columns = parsed
    lowered = {name.lower(): values for name, values in columns.items()}
    if "used" not in lowered or "free" not in lowered:
        return {"state": "legend_unrecognized", "legend": sorted(lowered)[:_MAX_LIST], "used_percent": None, "series": []}
    percents: list[float | None] = []
    for index in range(len(timestamps)):
        parts = [values[index] for values in lowered.values()]
        total = sum(part for part in parts if part is not None and part >= 0)
        used = lowered["used"][index]
        percents.append(100.0 * used / total if used is not None and total > 0 else None)
    series = _percent_series(timestamps, percents)
    return {
        "state": "observed" if series else "unavailable",
        "derivation": "used_over_sum_of_legend",
        "vertical_label": label,
        "used_percent": series[-1][1] if series else None,
        "series": series,
    }


def _network_from_graphs(graphs: list[object], label: str | None) -> dict[str, Any]:
    totals: dict[int, float] = {}
    names = []
    for graph in graphs:
        parsed = _graph_columns(graph)
        if parsed is None:
            continue
        timestamps, columns = parsed
        lowered = {name.lower(): values for name, values in columns.items()}
        received = lowered.get("received", lowered.get("rx"))
        sent = lowered.get("sent", lowered.get("tx"))
        if received is None or sent is None:
            continue
        names.append(str((graph or {}).get("identifier") or "")[:32])  # type: ignore[union-attr]
        for stamp, rx, tx in zip(timestamps, received, sent, strict=True):
            if rx is not None and tx is not None:
                totals[stamp] = totals.get(stamp, 0.0) + abs(rx) + abs(tx)
    series = [[stamp, round(totals[stamp], 3)] for stamp in sorted(totals)]
    return {
        "state": "observed" if series else "unavailable",
        "interfaces": names[:_MAX_LIST],
        "vertical_label": label,
        "throughput": series[-1][1] if series else None,
        "series": series,
    }


def _graph_labels(rows: object) -> dict[str, str]:
    labels: dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                labels[row["name"]] = str(row.get("vertical_label") or "")[:48]
    return labels


def collect_appliance_pulse(adapter: Any) -> dict[str, Any]:
    """Collect one pulse through the adapter; blocking, run in a thread."""
    with adapter.read_only_session(call_timeout=CALL_TIMEOUT_SECONDS) as client:
        session = _Session(client)
        info = session.optional("system_info", "system.info")
        alerts = session.optional("alerts", "alert.list")
        pools = session.optional("pools", "pool.query")
        interfaces = session.optional("interfaces", "interface.query")
        apps = session.optional("apps", "app.query")
        labels = _graph_labels(session.optional("graphs", "reporting.netdata_graphs"))
        network_section = _interfaces_section(interfaces)
        graphs = [{"name": "cpu", "identifier": None}, {"name": "memory", "identifier": None}]
        graphs += [{"name": "interface", "identifier": link["name"]} for link in network_section["physical"] if link["link_up"]][:4]
        series = session.optional(
            "netdata",
            "reporting.netdata_get_data",
            graphs,
            {"unit": "HOUR", "page": 1, "aggregate": True},
        )
    by_name: dict[str, list[Any]] = {}
    if isinstance(series, list):
        for graph in series:
            if isinstance(graph, dict):
                by_name.setdefault(str(graph.get("name")), []).append(graph)
    cpu = _cpu_from_graph((by_name.get("cpu") or [None])[0], labels.get("cpu"))
    memory = _memory_from_graph((by_name.get("memory") or [None])[0], labels.get("memory"))
    network = {**network_section, **_network_from_graphs(by_name.get("interface", []), labels.get("interface")), "state": network_section["state"]}
    payload: dict[str, Any] = {
        "appliance": _system_section(info),
        "cpu": cpu,
        "memory": memory,
        "network": network,
        "storage": _pools_section(pools),
        "alerts": _alerts_section(alerts),
        "apps": _apps_section(apps),
        "errors": session.errors,
        "window": "1h",
    }
    payload["impacts"] = derive_impacts(payload)
    payload["pressure_state"] = worst_state([impact["state"] for impact in payload["impacts"]])
    observed = [section for section in ("appliance", "storage", "alerts", "apps", "network") if payload[section].get("state") == "observed"]
    payload["state"] = "observed" if len(observed) == 5 and not session.errors else "partial" if observed else "telemetry_unavailable"
    return payload


def _base(observed_at: str) -> dict[str, Any]:
    return {"schema_version": 1, "model": MODEL, "source": SOURCE, "observed_at": observed_at, "synthetic": False}


async def fetch_appliance_pulse(*, adapter: Any | None = None, use_cache: bool = True) -> dict[str, Any]:
    """Return the cached pulse (30 s) or collect a new one under a deadline."""
    observed_at = utc_now()
    effective = adapter if adapter is not None else build_truenas_adapter()
    if effective is None:
        return {**_base(observed_at), "state": "not_configured", "reason": "truenas_credentials_missing"}
    now = time.monotonic()
    hit = _CACHE.get("pulse") if use_cache else None
    if hit and now - hit[0] < _CACHE_SECONDS:
        return {**deepcopy(hit[1]), "cached": True}
    async with _CACHE_LOCK:
        hit = _CACHE.get("pulse") if use_cache else None
        if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
            return {**deepcopy(hit[1]), "cached": True}
        try:
            collected = await asyncio.wait_for(asyncio.to_thread(collect_appliance_pulse, effective), timeout=DEADLINE_SECONDS)
            payload = {**_base(observed_at), **collected}
        except TimeoutError:
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": "timeout"}
        except TrueNASHealthProbeError as exc:
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": exc.stage, "phase": exc.phase}
        except Exception as exc:  # Transport errors are evidence, never a 500.
            payload = {**_base(observed_at), "state": "telemetry_unavailable", "reason": exc.__class__.__name__}
        if use_cache:
            _CACHE["pulse"] = (time.monotonic(), deepcopy(payload))
        return {**payload, "cached": False}


def reset_appliance_pulse_cache() -> None:
    _CACHE.clear()
