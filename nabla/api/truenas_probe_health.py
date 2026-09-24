"""Pure TrueNAS health helpers shared by the homelab probe orchestrator."""

from __future__ import annotations

from typing import Any, Literal

from nabla.integrations.truenas_client import truenas_host_port

HealthState = Literal["ok", "warn", "fail"]


def truenas_internal_target() -> tuple[str, int]:
    """Return the configured TrueNAS host/port used for internal reachability."""
    return truenas_host_port()


def truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    """Combine public, internal and API evidence into one TrueNAS health state."""
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    if api_reachable is False:
        return "fail"
    if public_state == "fail" and (
        internal_state == "ok" or api_reachable is True
    ):
        return "warn"
    if public_state == "fail":
        return "fail"
    if internal_state == "fail":
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"
