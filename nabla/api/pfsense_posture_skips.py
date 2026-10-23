"""Fail-fast pfSense posture payloads that protect the appliance from fan-out."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _empty_service_evidence() -> dict[str, Any]:
    return {
        "services_observed": False,
        "services": [],
        "service_summary": {
            "running": 0,
            "stopped": 0,
            "unknown": 0,
            "total": 0,
        },
        "resolver": {},
        "upstreams": [],
    }


def _skipped_endpoints(endpoint_names: Iterable[str], reason: str) -> dict[str, dict[str, Any]]:
    return {name: {"observed": False, "error": reason} for name in endpoint_names if name != "system"}


def auth_rejected_posture(endpoint_names: list[str]) -> dict[str, Any]:
    """Preflight returned 401: skip every deeper endpoint instead of repeating it."""
    return {
        "reachable": False,
        "transport_reachable": True,
        "api_authenticated": False,
        "api_evidence_state": "authentication_failed",
        "successful_endpoint_count": 0,
        "endpoint_count": len(endpoint_names),
        "endpoint_status": {
            "system": {
                "observed": False,
                "error": "HTTP 401",
                "http_status": 401,
            },
            **_skipped_endpoints(endpoint_names, "skipped_after_authentication_failure"),
        },
        **_empty_service_evidence(),
        "error_stage": "system",
        "error": "HTTP 401",
        "auth_fail_fast": True,
    }


def slow_preflight_posture(endpoint_names: list[str], elapsed_ms: int) -> dict[str, Any]:
    """Preflight succeeded slowly: report the control plane and skip deep probes."""
    return {
        "reachable": True,
        "transport_reachable": True,
        "api_authenticated": True,
        "api_evidence_state": "partial",
        "successful_endpoint_count": 1,
        "endpoint_count": len(endpoint_names),
        "endpoint_status": {
            "system": {
                "observed": True,
                "elapsed_ms": elapsed_ms,
            },
            **_skipped_endpoints(endpoint_names, "skipped_after_slow_preflight"),
        },
        **_empty_service_evidence(),
        "control_plane_state": "slow",
        "control_plane_elapsed_ms": elapsed_ms,
        "deep_probe_skipped": True,
        "reason": ("pfSense API preflight is slow; deeper posture fan-out was skipped to protect the appliance"),
    }
