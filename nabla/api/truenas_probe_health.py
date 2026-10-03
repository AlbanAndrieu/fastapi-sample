"""Pure TrueNAS health helpers shared by the homelab probe orchestrator."""

from __future__ import annotations

import os
from typing import Any, Literal

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
    # Host liveness and authenticated management capability are separate
    # signals. A failed API/WebSocket probe must not claim the appliance itself
    # is down while the HTTPS listener is still reachable.
    if public_state == "fail" and (
        internal_state == "ok"
        or api_reachable is True
        or wan_tls_reachable is True
    ):
        return "warn"
    if public_state == "fail":
        return "fail"
    if api_reachable is False or internal_state == "fail":
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
    preferred_ids = (
        ("wan_socket", "wan_tls")
        if any(stage.get("id") == "wan_tls" for stage in stages)
        else ("socket", "tls")
    )
    transport_states = {
        str(stage.get("state") or "")
        for stage in stages
        if stage.get("id") in preferred_ids
    }
    if public_state == "ok" and transport_states <= {"", "ok"}:
        return "ok"
    if public_state == "fail" and "ok" in transport_states:
        return "warn"
    if public_state == "fail":
        return "fail"
    if "fail" in transport_states or "blocked" in transport_states:
        return "warn"
    return "warn"
