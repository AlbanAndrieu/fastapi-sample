"""TrueNAS-specific probe orchestration for homelab health snapshots."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import httpx

from nabla.api import truenas_probe_health
from nabla.api.homelab_models import HomelabService
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.api.truenas_diagnostics import append_truenas_api_stages, append_truenas_http_stage, collect_truenas_network_diagnostics, unmeasured_truenas_network_diagnostics
from nabla.api.truenas_health_observer import observe_truenas_health_api, truenas_http_verify_ssl
from nabla.api.truenas_transport_diagnostics import homelab_wan_metadata
from nabla.integrations.truenas_client import TrueNASSettings, truenas_host_port, truenas_url
from nabla.settings.homelab import TrueNASProviderSettings

PROBE_TIMEOUT_SEC = 5.0
DIAGNOSTICS_BUDGET_SEC = 3.0


async def probe_truenas_public_https(
    semaphore: asyncio.Semaphore,
    *,
    configured_url: str,
    verify_ssl: bool,
    http_probe: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    timeout = httpx.Timeout(PROBE_TIMEOUT_SEC)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=verify_ssl) as client:
        return await http_probe(client, semaphore, service_id="truenas", name="TrueNAS HTTPS", url=configured_url)


async def probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
    http_probe: Callable[..., Awaitable[dict[str, Any]]],
    internal_probe: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Probe TrueNAS with its own TLS policy while overlapping independent stages."""
    configured_url = truenas_url().rstrip("/") + "/ui/signin"
    host, port = truenas_host_port()
    verify_ssl = truenas_http_verify_ssl()
    path_mode = "direct_lan" if homelab_runtime_detected() else "public_wan_haproxy"
    if path_mode == "direct_lan":
        connect_host, connect_port = truenas_probe_health.truenas_internal_target()
    else:
        connect_host = str(homelab_wan_metadata()["ipv4"])
        connect_port = port

    ws_path = TrueNASProviderSettings().websocket_path
    websocket_uri = TrueNASSettings(
        url=truenas_url(),
        verify_ssl=verify_ssl,
        websocket_path=ws_path,
    ).websocket_uri

    api_task = asyncio.create_task(observe_truenas_health_api())
    public_task = asyncio.create_task(
        probe_truenas_public_https(
            semaphore,
            configured_url=configured_url,
            verify_ssl=verify_ssl,
            http_probe=http_probe,
        ),
    )
    diagnostics_task = asyncio.create_task(
        asyncio.wait_for(
            collect_truenas_network_diagnostics(
                host=host,
                port=connect_port,
                websocket_uri=websocket_uri,
                connect_host=connect_host,
                verify_ssl=verify_ssl,
                path_mode=path_mode,
            ),
            timeout=DIAGNOSTICS_BUDGET_SEC,
        ),
    )
    internal_task: asyncio.Task[dict[str, Any]] | None = None
    if internal_enabled:
        internal_host, internal_port = truenas_probe_health.truenas_internal_target()
        internal_task = asyncio.create_task(
            internal_probe(
                semaphore,
                HomelabService(
                    name="TrueNAS TCP",
                    internalHost=internal_host,
                    internalPort=internal_port,
                    external=False,
                ),
            ),
        )

    managed_tasks = [api_task, public_task, diagnostics_task]
    if internal_task is not None:
        managed_tasks.append(internal_task)

    try:
        api_result, public_result = await asyncio.gather(
            api_task,
            public_task,
        )
        internal_result = await internal_task if internal_task is not None else None
        try:
            diagnostics = await diagnostics_task
        except TimeoutError:
            diagnostics = unmeasured_truenas_network_diagnostics(
                host=host,
                port=connect_port,
                websocket_uri=websocket_uri,
                verify_ssl=verify_ssl,
                path_mode=path_mode,
                budget_seconds=DIAGNOSTICS_BUDGET_SEC,
            )
            diagnostics["connect_target"] = f"{connect_host}:{connect_port}"
            diagnostics["server_name"] = host
    finally:
        for task in managed_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*managed_tasks, return_exceptions=True)

    diagnostics = append_truenas_http_stage(diagnostics, public_result)
    public_ingress_state = truenas_probe_health.truenas_public_ingress_state(
        public_result,
        diagnostics,
    )
    appliance_state = truenas_probe_health.truenas_appliance_state(
        public_result,
        internal_result,
        api_result,
    )
    state = truenas_probe_health.truenas_state(
        public_result,
        internal_result,
        api_result,
        wan_tls_reachable=diagnostics.get("wan_tls_reachable"),
    )
    diagnostics = append_truenas_api_stages(diagnostics, api_result)
    return {
        "id": "truenas",
        "state": state,
        "appliance_state": appliance_state,
        "public_ingress_state": public_ingress_state,
        "public": public_result,
        "internal": internal_result,
        "api": api_result,
        "diagnostics": diagnostics,
        "internal_probe_enabled": internal_enabled,
        "verify_ssl": verify_ssl,
        "path_mode": path_mode,
        "connect_host": connect_host,
        "connect_port": connect_port,
    }
