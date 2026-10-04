"""Normalized multidimensional health contract shared by provider/service probes."""

from __future__ import annotations

from typing import Any

HealthState = str
_HEALTH_STATES = frozenset({"ok", "warn", "fail", "unknown"})


def normalize_health_state(value: object, *, default: HealthState = "unknown") -> HealthState:
    """Normalize heterogeneous probe/provider states to the public health vocabulary."""
    state = str(value or "").strip().lower()
    return state if state in _HEALTH_STATES else default


def build_health_model(
    *,
    service_state: object = "unknown",
    transport_state: object = "unknown",
    authentication_state: object = "unknown",
    application_state: object = "unknown",
    runtime_state: object = "unknown",
    dependency_state: object = "unknown",
    effective_state: object = "unknown",
) -> dict[str, HealthState]:
    """Return the stable seven-axis health model used by the API health board."""
    return {
        "service_state": normalize_health_state(service_state),
        "transport_state": normalize_health_state(transport_state),
        "authentication_state": normalize_health_state(authentication_state),
        "application_state": normalize_health_state(application_state),
        "runtime_state": normalize_health_state(runtime_state),
        "dependency_state": normalize_health_state(dependency_state),
        "effective_state": normalize_health_state(effective_state),
    }


def attach_health_model(payload: dict[str, Any], **states: object) -> dict[str, Any]:
    """Attach the normalized model while preserving legacy evidence fields."""
    result = dict(payload)
    result["health_model"] = build_health_model(**states)
    return result
