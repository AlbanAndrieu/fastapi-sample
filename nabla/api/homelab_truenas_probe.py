"""TrueNAS-specific HTTPS, TCP, WebSocket and diagnostics probe orchestration."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal

import httpx

from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_runner import (
    _probe_http_endpoint,
    _probe_internal_service,
)
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.api.truenas_diagnostics import (
    append_truenas_api_stages,
    collect_truenas_network_diagnostics,
    unmeasured_truenas_network_diagnostics,
)
from nabla.api.truenas_health_observer import (
    observe_truenas_health_api as _observe_truenas_api,
    truenas_http_verify_ssl,
)
from nabla.integrations.truenas_client import (
    TrueNASSettings,
    truenas_host_port,
    truenas_url,
)

HealthState = Literal["ok", "warn", "fail"]
_PROBE_TIMEOUT_SEC = 5.0
_TRUENAS_DIAGNOSTICS_BUDGET_SEC = 3.0


def _truenas_internal_target(
    _services: list[HomelabService] | None = None,
) -> tuple[str, int]:
    return truenas_host_port()


def _truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    """Prioritize authenticated API evidence, then endpoint/path evidence."""
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    api_stale = bool(api_result and api_result.get("stale"))

    # A stale last-good keeps the platform diagnosable but does not prove a fresh
    # outage. Fresh authenticated API failure remains authoritative for TrueNAS.
    if api_reachable is False and not api_stale:
        return "fail"
    if api_reachable is False and api_stale:
        if internal_state == "ok" or public_state in {"ok", "warn"}:
            return "warn"
        return "warn"
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if internal_state == "fail":
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"


async def _probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
) -> dict[str, Any]:
    """Probe TrueNAS while overlapping independent API/TCP diagnostics."""
    configured_url = truenas_url().rstrip("/") + "/"
    api_task = asyncio.create_task(_observe_truenas_api())
    internal_task: asyncio.Task[dict[str, Any]] | None = None
    if internal_enabled:
        host, port = _truenas_internal_target()
        internal_task = asyncio.create_task(
            _probe_internal_service(
                semaphore,
                HomelabService(
                    name="TrueNAS TCP",
                    internalHost=host,
                    internalPort=port,
                    external=False,
                ),
            ),
        )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_PROBE_TIMEOUT_SEC),
        follow_redirects=False,
        verify=truenas_http_verify_ssl(),
    ) as truenas_client:
        public_result = await _probe_http_endpoint(
            truenas_client,
            semaphore,
            service_id="truenas",
            name="TrueNAS HTTPS",
            url=configured_url,
        )

    host, port = truenas_host_port()
    verify_ssl = truenas_http_verify_ssl()
    ws_path = os.getenv("TRUENAS_WS_PATH", "/api/current").strip() or "/api/current"
    websocket_uri = TrueNASSettings(
        url=truenas_url(),
        verify_ssl=verify_ssl,
        websocket_path=ws_path,
    ).websocket_uri
    path_mode = "direct_lan" if homelab_runtime_detected() else "public_wan_haproxy"
    diagnostics_task = asyncio.create_task(
        collect_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            public_result=public_result,
            path_mode=path_mode,
        ),
    )

    api_result = await api_task
    internal_result = await internal_task if internal_task is not None else None
    try:
        diagnostics = await asyncio.wait_for(
            diagnostics_task,
            timeout=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    except TimeoutError:
        diagnostics_task.cancel()
        await asyncio.gather(diagnostics_task, return_exceptions=True)
        diagnostics = unmeasured_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            path_mode=path_mode,
            budget_seconds=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    diagnostics = append_truenas_api_stages(diagnostics, api_result)
    return {
        "id": "truenas",
        "state": _truenas_state(public_result, internal_result, api_result),
        "public": public_result,
        "internal": internal_result,
        "api": api_result,
        "diagnostics": diagnostics,
        "internal_probe_enabled": internal_enabled,
        "verify_ssl": verify_ssl,
    }
