"""Pure TrueNAS health helpers shared by the homelab probe orchestrator."""

from __future__ import annotations

import os
from typing import Any, Literal

from nabla.api.service_health_model import build_health_model

HealthState = Literal["ok", "warn", "fail"]
_DEFAULT_TRUENAS_LAN_HOST = "172.17.0.24"
_DEFAULT_TRUENAS_LAN_PORT = 7000


def truenas_internal_target() -> tuple[str, int]:
    """Return the explicit LAN address used for appliance liveness."""
    host = os.getenv("TRUENAS_LAN_HOST", _DEFAULT_TRUENAS_LAN_HOST).strip()
    raw_port = os.getenv(
        "TRUENAS_LAN_PORT",
        str(_DEFAULT_TRUENAS_LAN_PORT),
    ).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = _DEFAULT_TRUENAS_LAN_PORT
    return host or _DEFAULT_TRUENAS_LAN_HOST, port


def truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
    *,
    wan_tls_reachable: bool | None = None,
) -> HealthState:
    """Combine public, internal and API evidence into one TrueNAS health state."""
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    api_degraded = False
    if isinstance(api_result, dict) and api_reachable is True:
        readiness = api_result.get("readiness") if isinstance(api_result.get("readiness"), dict) else {}
        version = api_result.get("system_version") if isinstance(api_result.get("system_version"), dict) else {}
        inventory = api_result.get("app_inventory") if isinstance(api_result.get("app_inventory"), dict) else {}
        api_degraded = (
            api_result.get("system_ready") is False
            or str(readiness.get("state") or "ok").lower() != "ok"
            or str(version.get("state") or "ok").lower() != "ok"
            or str(inventory.get("state") or "ok").lower() != "ok"
        )
    # Host liveness and authenticated management capability are separate
    # signals. A failed API/WebSocket probe must not claim the appliance itself
    # is down while the HTTPS listener is still reachable.
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True or wan_tls_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if api_reachable is False or internal_state == "fail":
        return "warn"
    if api_degraded:
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"


def truenas_appliance_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    """Rate appliance liveness independently from the public WAN ingress."""
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    public_state = public_result.get("state")

    if api_reachable is True or internal_state == "ok":
        return "ok"
    if api_reachable is False and internal_state == "fail":
        return "fail"
    if public_state == "ok":
        return "warn" if api_reachable is False or internal_state == "fail" else "ok"
    return "warn" if api_reachable is False or internal_state == "fail" else "fail"


def truenas_public_ingress_state(
    public_result: dict[str, Any],
    diagnostics: dict[str, Any] | None,
) -> HealthState:
    """Rate the pfSense/HAProxy :7000 ingress without using API success."""
    public_state = str(public_result.get("state") or "").strip().lower()
    stages = diagnostics.get("stages", []) if isinstance(diagnostics, dict) else []
    tls_id = "wan_tls" if any(stage.get("id") == "wan_tls" for stage in stages) else "tls"
    tls_stage = next(
        (stage for stage in stages if stage.get("id") == tls_id),
        None,
    )
    tls_state = str(tls_stage.get("state") or "") if isinstance(tls_stage, dict) else ""

    if public_state == "ok" and tls_state in {"", "ok"}:
        return "ok"
    if public_state == "fail" and tls_state == "ok":
        return "warn"
    if public_state == "fail":
        return "fail"
    if tls_state in {"fail", "blocked"}:
        return "warn"
    return "warn"



def truenas_health_model(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None,
    *,
    appliance_state: HealthState,
    effective_state: HealthState,
) -> dict[str, str]:
    """Describe TrueNAS transport/auth/RPC/runtime health as separate axes."""
    stages = diagnostics.get("stages", []) if isinstance(diagnostics, dict) else []
    websocket = next(
        (stage for stage in stages if isinstance(stage, dict) and stage.get("id") == "websocket"),
        {},
    )
    public_state = str(public_result.get("state") or "").strip().lower()
    internal_state = (
        str(internal_result.get("state") or "").strip().lower()
        if isinstance(internal_result, dict)
        else ""
    )
    websocket_state = str(websocket.get("state") or "").strip().lower()
    transport_evidence = {state for state in (public_state, internal_state, websocket_state) if state}
    if "ok" in transport_evidence:
        transport_state = "warn" if "fail" in transport_evidence else "ok"
    elif "warn" in transport_evidence:
        transport_state = "warn"
    elif "fail" in transport_evidence:
        transport_state = "fail"
    else:
        transport_state = "unknown"

    api = api_result if isinstance(api_result, dict) else {}
    reachable = api.get("reachable") is True
    authenticated = api.get("authenticated") is True
    phase = str(api.get("phase") or "").strip().lower()
    stage = str(api.get("stage") or "").strip().lower()
    if reachable or authenticated:
        authentication_state = "ok"
    elif phase == "authentication" or stage in {
        "authentication",
        "missing_api_key",
        "missing_username",
        "invalid_api_key_reference",
        "invalid_api_key_format",
    }:
        authentication_state = "fail"
    elif api:
        authentication_state = "unknown"
    else:
        authentication_state = "unknown"

    readiness = api.get("readiness") if isinstance(api.get("readiness"), dict) else {}
    version = api.get("system_version") if isinstance(api.get("system_version"), dict) else {}
    inventory = api.get("app_inventory") if isinstance(api.get("app_inventory"), dict) else {}
    if reachable:
        application_state = (
            "warn"
            if (
                api.get("system_ready") is False
                or str(readiness.get("state") or "ok").lower() != "ok"
                or str(version.get("state") or "ok").lower() != "ok"
                or str(inventory.get("state") or "ok").lower() != "ok"
            )
            else "ok"
        )
    elif authenticated or phase == "call":
        application_state = "warn"
    else:
        application_state = "unknown"

    return build_health_model(
        service_state=appliance_state,
        transport_state=transport_state,
        authentication_state=authentication_state,
        application_state=application_state,
        runtime_state=appliance_state,
        dependency_state="ok",
        effective_state=effective_state,
    )
