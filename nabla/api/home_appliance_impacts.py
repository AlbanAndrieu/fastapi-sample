"""Same-snapshot associations between live TrueNAS appliance signals.

An impact links two sections observed in the same pulse (storage ↔ alerts,
memory ↔ crashed Apps, load ↔ services, physical links ↔ services). It is an
association with its evidence, never a causal claim.
"""

from __future__ import annotations

import re
from typing import Any

FAIL_LEVELS = frozenset({"CRITICAL", "ERROR", "ALERT", "EMERGENCY"})
WARN_LEVELS = frozenset({"WARNING", "NOTICE"})
_STORAGE_ALERT = re.compile(r"pool|quota|space|capacity|scrub|zfs", re.I)
_APP_ALERT = re.compile(r"app|docker|container|image", re.I)
_TEXT_LIMIT = 160
_MAX_LIST = 20


def worst_state(states: list[str]) -> str:
    for candidate in ("fail", "warn", "ok"):
        if candidate in states:
            return candidate
    return "unknown"


def derive_impacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Same-snapshot associations between appliance signals; never causality."""
    impacts: list[dict[str, Any]] = []
    alerts = payload["alerts"]
    pools = payload["storage"]
    apps = payload["apps"]
    system = payload["appliance"]
    active_alerts = [item for item in alerts.get("items", []) if not item["dismissed"]]

    def add(impact_id: str, source: str, target: str, state: str, evidence: str, linked: list[str] | None = None) -> None:
        impacts.append({"id": impact_id, "from": source, "to": target, "state": state, "evidence": evidence[:_TEXT_LIMIT], "linked": (linked or [])[:_MAX_LIST]})

    worst = pools.get("worst_used_percent")
    if worst is not None:
        storage_alerts = [item["klass"] for item in active_alerts if _STORAGE_ALERT.search(item["klass"])]
        state = "fail" if worst >= 90 else "warn" if worst >= 80 else "ok"
        add("storage_capacity", "storage", "alerts", state, f"pool le plus plein à {worst:.1f} % ; {len(storage_alerts)} alerte(s) stockage active(s)", storage_alerts)
    unhealthy = [pool["name"] for pool in pools.get("pools", []) if not pool["healthy"]]
    if pools.get("state") == "observed":
        add(
            "pool_health",
            "storage",
            "services",
            "fail" if unhealthy else "ok",
            "pools dégradés : " + ", ".join(unhealthy) if unhealthy else "tous les pools sont sains",
            unhealthy,
        )
    per_core = system.get("load_per_core_1m")
    if per_core is not None:
        cpu = payload["cpu"].get("busy_percent")
        state = "fail" if per_core >= 1.5 else "warn" if per_core >= 1.0 else "ok"
        add("cpu_pressure", "cpu", "services", state, f"charge 1 min {per_core:.2f} par cœur" + (f" ; CPU occupé {cpu:.0f} %" if cpu is not None else ""))
    used = payload["memory"].get("used_percent")
    if used is not None:
        crashed = apps.get("crashed", [])
        state = "fail" if used >= 95 else "warn" if used >= 90 else "ok"
        add("memory_pressure", "memory", "apps", state, f"mémoire utilisée {used:.0f} % ; {len(crashed)} App(s) CRASHED dans le même instantané", crashed)
    if apps.get("state") == "observed":
        app_alerts = [item["klass"] for item in active_alerts if _APP_ALERT.search(item["klass"])]
        counts = apps["counts"]
        state = "fail" if counts.get("CRASHED") else "warn" if counts.get("DEPLOYING") else "ok"
        add(
            "app_fleet",
            "apps",
            "alerts",
            state,
            f"{counts.get('RUNNING', 0)} RUNNING, {counts.get('STOPPED', 0)} STOPPED, {counts.get('CRASHED', 0)} CRASHED, {counts.get('DEPLOYING', 0)} DEPLOYING",
            app_alerts,
        )
    if alerts.get("state") == "observed":
        levels = alerts["by_level"]
        state = "fail" if any(level in FAIL_LEVELS for level in levels) else "warn" if any(level in WARN_LEVELS for level in levels) else "ok"
        add(
            "active_alerts",
            "alerts",
            "appliance",
            state,
            f"{alerts['active']} alerte(s) active(s) : " + ", ".join(f"{level} {count}" for level, count in sorted(levels.items())) if levels else "aucune alerte active",
        )
    links_down = payload["network"].get("links_down", [])
    if payload["network"].get("state") == "observed":
        add(
            "network_links",
            "network",
            "services",
            "warn" if links_down else "ok",
            "liens physiques inactifs : " + ", ".join(links_down) if links_down else "tous les liens physiques sont actifs",
            links_down,
        )
    return impacts
