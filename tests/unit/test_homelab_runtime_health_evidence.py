"""Tests for runtime-specific homelab service-health reconciliation."""

import asyncio

from nabla.api import homelab_health_evidence as module
from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)
from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import (
    ObservedApp,
    ObservedContainer,
    TrueNASRuntimeSnapshot,
)
from nabla.api.homelab_topology import HomelabTopology


def _runtime(*apps: ObservedApp) -> TrueNASRuntimeSnapshot:
    return TrueNASRuntimeSnapshot(
        observed_at="2026-08-26T15:00:00Z",
        configured=True,
        reachable=True,
        apps=list(apps),
    )


def test_down_tunnel_is_degraded_when_origin_is_proven_up() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnelUrl="https://2fauth.albandrieu.com",
        internalHost="172.17.0.24",
        internalPort=30081,
        external=True,
    )
    tunnel = CloudflareTunnelObservation(
        tunnel_id="tunnel-1",
        name="homelab",
        status="down",
        config_source="cloudflare",
        ingress=(
            CloudflareTunnelIngress(
                tunnel_id="tunnel-1",
                tunnel_name="homelab",
                hostname="2fauth.albandrieu.com",
                service="http://2fauth:8000",
                status="down",
            ),
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://2fauth.albandrieu.com/",
                "reachable": True,
                "http_status": 403,
                "state": "warn",
                "tls_trusted": True,
            },
        ],
        internal_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "host": "172.17.0.24",
                "port": 30081,
                "reachable": True,
                "state": "ok",
            },
        ],
        runtime=None,
        tunnels=[tunnel],
    )

    assert rows[0]["state"] == "warn"


def test_declared_container_binding_maps_openwebui_runtime() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://open-webui.albandrieu.com",
        external=True,
    )
    runtime = _runtime(
        ObservedApp(
            app_id="openwebui",
            name="openwebui",
            state="DEPLOYING",
            containers=[
                ObservedContainer(
                    service_name="open-webui",
                    image="ghcr.io/open-webui/open-webui:v0.11.0",
                    state="starting",
                ),
            ],
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://open-webui.albandrieu.com/",
                "reachable": True,
                "http_status": 403,
                "state": "warn",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                containerService="open-webui",
            ),
        },
    )

    assert rows[0]["runtime_app"] == "openwebui"
    assert rows[0]["runtime_state"] == "DEPLOYING"
    assert rows[0]["state"] == "fail"


def test_declared_app_id_maps_twofactor_auth_runtime() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnelUrl="https://2fauth.albandrieu.com",
        external=True,
    )
    runtime = _runtime(
        ObservedApp(
            app_id="twofactor-auth",
            name="twofactor-auth",
            state="DEPLOYING",
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://2fauth.albandrieu.com/",
                "reachable": True,
                "http_status": 302,
                "state": "ok",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                appId="twofactor-auth",
            ),
        },
    )

    assert rows[0]["runtime_app"] == "twofactor-auth"
    assert rows[0]["runtime_state"] == "DEPLOYING"
    assert rows[0]["state"] == "fail"


def test_deploying_runtime_is_degraded_when_origin_is_proven_up() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://open-webui.albandrieu.com",
        external=True,
    )
    runtime = _runtime(
        ObservedApp(app_id="openwebui", name="openwebui", state="DEPLOYING"),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://open-webui.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                appId="openwebui",
            ),
        },
    )

    assert rows[0]["state"] == "warn"


def test_exact_app_id_keeps_stopped_runtime_visible_without_container_details() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://open-webui.albandrieu.com",
        external=True,
    )
    runtime = _runtime(
        ObservedApp(
            app_id="openwebui",
            name="openwebui",
            state="STOPPED",
            containers=[],
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                appId="openwebui",
                containerService="open-webui",
            ),
        },
    )

    assert rows[0]["runtime_app"] == "openwebui"
    assert rows[0]["runtime_state"] == "STOPPED"
    assert rows[0]["state"] == "fail"


def test_missing_declared_truenas_app_is_failure_even_with_healthy_tunnel() -> None:
    service = HomelabService(
        name="Keycloak",
        tunnelUrl="https://keycloak.albandrieu.com",
        external=True,
    )
    tunnel = CloudflareTunnelObservation(
        tunnel_id="tunnel-1",
        name="homelab",
        status="healthy",
        config_source="cloudflare",
        ingress=(
            CloudflareTunnelIngress(
                tunnel_id="tunnel-1",
                tunnel_name="homelab",
                hostname="keycloak.albandrieu.com",
                service="http://keycloak:8080",
                status="healthy",
            ),
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=_runtime(),
        tunnels=[tunnel],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                containerService="keycloak",
            ),
        },
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["runtime_state"] is None
    assert rows[0]["runtime_app"] is None
    assert rows[0]["runtime_missing"] is True
    assert rows[0]["tunnel_status"] == "healthy"


def test_missing_runtime_binding_with_fresh_origin_is_drift_not_outage() -> None:
    service = HomelabService(
        name="Vaultwarden",
        tunnelUrl="https://vaultwarden.albandrieu.com",
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": "Vaultwarden",
                "url": "https://vaultwarden.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=_runtime(),
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                containerService="vaultwarden",
            ),
        },
    )

    assert rows[0]["runtime_missing"] is True
    assert rows[0]["direct_state"] == "ok"
    assert rows[0]["state"] == "warn"


def test_stale_runtime_does_not_claim_declared_app_is_missing() -> None:
    service = HomelabService(
        name="Keycloak",
        tunnelUrl="https://keycloak.albandrieu.com",
        external=True,
    )
    runtime = _runtime().model_copy(update={"stale": True})
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
        runtime_bindings={
            service.service_id: RuntimeBinding(
                provider="truenas-app",
                containerService="keycloak",
            ),
        },
    )

    assert rows[0]["runtime_missing"] is False
    assert rows[0]["state"] == "unknown"


def test_runtime_error_is_exposed_in_reconciled_payload(monkeypatch) -> None:
    service = HomelabService(
        name="TrueNAS-dependent service",
        tunnelUrl="https://example.albandrieu.com",
        external=True,
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-09-08T03:00:00Z",
        configured=True,
        reachable=False,
        error="You are not allowed to access this resource",
    )

    async def _services():
        return [service]

    async def _declared():
        class Catalog:
            services = []

        return Catalog()

    async def _runtime_snapshot():
        return runtime

    async def _cloudflare():
        class Cloudflare:
            tunnels = []
            access_applications = []
            stale = False
            configured = False

            def summary(self):
                return {}

        return Cloudflare()

    async def _topology():
        return HomelabTopology()

    async def _dns(**_kwargs):
        return {}

    monkeypatch.setattr(module, "fetch_homelab_services", _services)
    monkeypatch.setattr(module, "fetch_declared_service_catalog", _declared)
    monkeypatch.setattr(module, "fetch_truenas_runtime", _runtime_snapshot)
    monkeypatch.setattr(module, "observe_cloudflare_exposure", _cloudflare)
    monkeypatch.setattr(module, "fetch_homelab_topology", _topology)
    monkeypatch.setattr(module, "observe_pfsense_dns_posture", _dns)

    payload = asyncio.run(module.reconcile_homelab_health_payload({"services": []}))

    assert payload["truenas_runtime_reachable"] is False
    assert payload["truenas_runtime_error"] == "You are not allowed to access this resource"
