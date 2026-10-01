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
) -> HealthState:
    """Combine public, internal and API evidence into one TrueNAS health state."""
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    # Host liveness and authenticated management capability are separate
    # signals. A failed API/WebSocket probe must not claim the appliance itself
    # is down while the HTTPS listener is still reachable.
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if api_reachable is False or internal_state == "fail":
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"
