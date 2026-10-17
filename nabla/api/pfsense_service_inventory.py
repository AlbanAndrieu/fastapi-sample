"""Sanitized pfSense service inventory and security-filter observations.

Extracted from ``pfsense_dns_observer`` so the DNS posture observer keeps its
HTTP/cache orchestration while these pure, non-secret classifiers stay small.
"""

from __future__ import annotations

from typing import Any

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_RUNNING_STATES = frozenset({"active", "healthy", "running", "started", "up"})
_STOPPED_STATES = frozenset({"crashed", "down", "error", "failed", "stopped"})
_SECURITY_SERVICE_MATCHERS = {
    "snort": ("snort",),
    "pfblockerng": ("pfblocker", "pfb_filter", "pfb_dnsbl"),
    "crowdsec": ("crowdsec",),
}
_SECURITY_SERVICE_LABELS = {
    "snort": "Snort",
    "pfblockerng": "pfBlockerNG",
    "crowdsec": "CrowdSec",
}


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return None


def _service_identity(row: dict[str, Any]) -> str:
    normalized = str(row.get("identity") or "").strip().casefold()
    if normalized:
        return normalized
    return " ".join(str(row.get(key) or "") for key in ("name", "service", "description", "title")).casefold()


def _service_runtime_state(row: dict[str, Any]) -> str:
    normalized = str(row.get("runtime_state") or "").strip().casefold()
    if normalized in {"running", "stopped", "unknown"}:
        return normalized
    for key in ("running", "active", "enabled"):
        parsed = _optional_bool(row.get(key))
        if parsed is not None:
            return "running" if parsed else "stopped"
    status = str(row.get("status") or row.get("state") or "").strip().casefold()
    if status in _RUNNING_STATES:
        return "running"
    if status in _STOPPED_STATES:
        return "stopped"
    return "unknown"


def _sanitize_services(services: object) -> list[dict[str, str]]:
    if not isinstance(services, list):
        return []
    return [
        {
            "identity": _service_identity(row),
            "runtime_state": _service_runtime_state(row),
        }
        for row in services
        if isinstance(row, dict)
    ]


def _service_running(services: object) -> bool | None:
    if not isinstance(services, list):
        return None
    for row in services:
        if not isinstance(row, dict):
            continue
        identity = _service_identity(row)
        if "unbound" not in identity and "dns resolver" not in identity:
            continue
        state = _service_runtime_state(row)
        if state == "running":
            return True
        if state == "stopped":
            return False
        return None
    return None


def _service_summary(services: list[dict[str, str]]) -> dict[str, int]:
    summary = {"running": 0, "stopped": 0, "unknown": 0}
    for service in services:
        state = service.get("runtime_state", "unknown")
        summary[state if state in summary else "unknown"] += 1
    summary["total"] = len(services)
    return summary


_SNORT_ATTRIBUTION_NOT_AUTHORITATIVE = (
    "observed",
    "snort2c telemetry exists but current egress attribution is not authoritative",
)
_SNORT_INGRESS_FILTER_STATES: dict[str, tuple[str, str]] = {
    "clear": (
        "clear",
        "snort2c telemetry is reachable and the observed FastAPI egress is not blocked",
    ),
    "attribution_unavailable": _SNORT_ATTRIBUTION_NOT_AUTHORITATIVE,
    "telemetry_stale": _SNORT_ATTRIBUTION_NOT_AUTHORITATIVE,
    "telemetry_unavailable": ("unknown", "snort2c telemetry is unavailable"),
}


def _firewall_filter(
    *,
    snort_blocked: bool,
    posture_authenticated: bool | None,
) -> dict[str, str]:
    if snort_blocked:
        firewall_state = "blocked"
        firewall_detail = "PF is enforcing the snort2c block for the observed FastAPI egress"
    elif posture_authenticated is False:
        firewall_state = "warn"
        firewall_detail = "pfSense/PF is on the declared path, but posture API authentication failed; path presence is not promoted to healthy"
    else:
        firewall_state = "in_path"
        firewall_detail = "pfSense/PF is on the declared path; this is path evidence, not a health or authentication verdict"
    return {
        "id": "firewall",
        "label": "pfSense/PF firewall",
        "state": firewall_state,
        "detail": firewall_detail,
    }


def _matched_services_state(matches: list[dict[str, Any]]) -> tuple[str, str]:
    states = {_service_runtime_state(row) for row in matches}
    if "running" in states:
        state = "running"
    elif states == {"stopped"}:
        state = "stopped"
    else:
        state = "unknown"
    return state, f"{len(matches)} service entr{'y' if len(matches) == 1 else 'ies'} observed"


def _security_filter_state(
    filter_id: str,
    matches: list[dict[str, Any]],
    *,
    snort_blocked: bool,
    ingress_state: str,
    inventory_observed: bool,
) -> tuple[str, str]:
    """Return ``(state, detail)`` for one security service filter."""
    if filter_id == "snort" and snort_blocked:
        return "blocked", "Observed FastAPI egress is present in the Snort snort2c PF table"
    if matches:
        return _matched_services_state(matches)
    if filter_id == "snort" and ingress_state in _SNORT_INGRESS_FILTER_STATES:
        return _SNORT_INGRESS_FILTER_STATES[ingress_state]
    if not inventory_observed:
        return "unknown", "Service inventory was not observed because /api/v2/status/services did not succeed"
    return "not_observed", "Not present in the successful /api/v2/status/services inventory"


def _security_filter_observations(
    services: object,
    *,
    ingress_block: dict[str, Any] | None = None,
    services_observed: bool | None = None,
    posture_authenticated: bool | None = None,
) -> list[dict[str, str]]:
    ingress_state = str((ingress_block or {}).get("state") or "unknown")
    snort_blocked = ingress_state == "blocked"
    inventory_observed = isinstance(services, list) if services_observed is None else services_observed
    filters: list[dict[str, str]] = [
        _firewall_filter(
            snort_blocked=snort_blocked,
            posture_authenticated=posture_authenticated,
        ),
    ]
    service_rows = [row for row in services if isinstance(row, dict)] if isinstance(services, list) else []
    for filter_id, matchers in _SECURITY_SERVICE_MATCHERS.items():
        matches = [row for row in service_rows if any(matcher in _service_identity(row) for matcher in matchers)]
        state, detail = _security_filter_state(
            filter_id,
            matches,
            snort_blocked=snort_blocked,
            ingress_state=ingress_state,
            inventory_observed=inventory_observed,
        )
        filters.append(
            {
                "id": filter_id,
                "label": _SECURITY_SERVICE_LABELS[filter_id],
                "state": state,
                "detail": detail,
            },
        )
    return filters
