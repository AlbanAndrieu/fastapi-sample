"""Tests for multi-source homelab health reconciliation."""

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


def test_private_running_service_is_green_without_external_probe() -> None:
    service = HomelabService(
        name="Hello",
        internalHost="172.17.0.24",
        internalPort=8099,
        external=False,
        healthNote="⚠️ Internal-only service; functional probe requires the homelab observer.",
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=_runtime(ObservedApp(app_id="hello", name="hello", state="RUNNING")),
        tunnels=[],
    )

    assert rows[0]["state"] == "ok"
    assert rows[0]["health_note"].startswith("⚠️ Internal-only")
    assert rows[0]["runtime_state"] == "RUNNING"
    assert rows[0]["runtime_app"] == "hello"
    assert rows[0]["http_status"] == 0


def test_private_service_is_green_when_internal_probe_succeeds() -> None:
    service = HomelabService(
        name="Hello",
        tunnelUrl="https://hello.int.albandrieu.com",
        internalHost="172.17.0.24",
        internalPort=8099,
        external=False,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[
            {
                "id": service.service_id,
                "name": "Hello",
                "host": "172.17.0.24",
                "port": 8099,
                "reachable": True,
                "state": "ok",
            },
        ],
        runtime=_runtime(ObservedApp(app_id="hello", name="hello", state="RUNNING")),
        tunnels=[],
    )

    assert rows[0]["state"] == "ok"
    assert rows[0]["internal_state"] == "ok"


def test_cloudflare_protected_service_is_warning_not_failure() -> None:
    service = HomelabService(
        name="SearXNG",
        tunnelUrl="https://searxng.albandrieu.com",
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
                hostname="searxng.albandrieu.com",
                service="http://searxng:8080",
                status="healthy",
            ),
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": "SearXNG",
                "url": "https://searxng.albandrieu.com/",
                "reachable": False,
                "http_status": 0,
                "state": "fail",
                "tls_trusted": None,
                "error": "probe blocked",
            },
        ],
        internal_results=[],
        runtime=_runtime(ObservedApp(app_id="searxng", name="SearXNG", state="RUNNING")),
        tunnels=[tunnel],
    )

    assert rows[0]["state"] == "warn"
    assert rows[0]["direct_state"] == "fail"
    assert rows[0]["runtime_state"] == "RUNNING"
    assert rows[0]["tunnel_status"] == "healthy"
    assert rows[0]["tunnel_name"] == "homelab"


def test_direct_403_stays_warning_with_cloudflare_access() -> None:
    service = HomelabService(
        name="SearXNG",
        tunnelUrl="https://searxng.albandrieu.com",
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": "SearXNG",
                "url": "https://searxng.albandrieu.com/",
                "reachable": True,
                "http_status": 403,
                "state": "warn",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["state"] == "warn"
    assert rows[0]["http_status"] == 403


def test_direct_success_remains_green_without_conflicting_evidence() -> None:
    service = HomelabService(
        name="Public service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://service.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["state"] == "ok"


def test_service_without_url_gets_conventional_endpoint_and_unknown_state() -> None:
    service = HomelabService(name="Prometheus", external=False)
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=None,
        tunnels=[],
    )

    assert rows == [
        {
            "id": "prometheus",
            "name": "Prometheus",
            "url": "https://prometheus.albandrieu.com/",
            "url_derived": True,
            "reachable": False,
            "http_status": 0,
            "state": "unknown",
            "tls_trusted": None,
            "direct_state": None,
            "internal_state": None,
            "runtime_state": None,
            "runtime_app": None,
            "runtime_missing": False,
            "runtime_reachable": None,
            "observed_at": None,
            "observation_age_seconds": None,
            "observation_stale": False,
        },
    ]


def test_application_error_is_degraded_when_service_is_still_reachable() -> None:
    service = HomelabService(
        name="LanguageTool",
        tunnelUrl="https://languagetool.albandrieu.com",
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://languagetool.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "fail",
                "tls_trusted": True,
                "application_error": "Application error",
            },
        ],
        internal_results=[],
        runtime=_runtime(
            ObservedApp(app_id="languagetool", name="LanguageTool", state="RUNNING"),
        ),
        tunnels=[],
    )

    assert rows[0]["state"] == "warn"
    assert rows[0]["application_error"] == "Application error"


def test_runtime_failure_overrides_public_edge_success() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnelUrl="https://2fauth.albandrieu.com",
        external=True,
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
        runtime=_runtime(
            ObservedApp(app_id="2fauth", name="2FAuth", state="STOPPED"),
        ),
        tunnels=[],
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["runtime_state"] == "STOPPED"


def test_healthy_tunnel_does_not_rescue_failed_origin_probe() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://open-webui.albandrieu.com",
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
                hostname="open-webui.albandrieu.com",
                service="https://open-webui:8080",
                status="healthy",
            ),
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://open-webui.albandrieu.com/",
                "reachable": False,
                "http_status": 0,
                "state": "fail",
                "tls_trusted": None,
                "error": "origin unavailable",
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[tunnel],
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["tunnel_status"] == "healthy"


def test_stale_runtime_cannot_rescue_failed_public_probe() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnelUrl="https://2fauth.albandrieu.com",
        external=True,
    )
    runtime = _runtime(
        ObservedApp(app_id="2fauth", name="2FAuth", state="RUNNING"),
    ).model_copy(update={"stale": True})
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://2fauth.albandrieu.com/",
                "reachable": False,
                "http_status": 0,
                "state": "fail",
                "tls_trusted": None,
            },
        ],
        internal_results=[],
        runtime=runtime,
        tunnels=[],
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["runtime_state"] == "RUNNING"
    assert rows[0]["runtime_stale"] is True


def test_stale_cloudflare_tunnel_cannot_rescue_failed_public_probe() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://open-webui.albandrieu.com",
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
                hostname="open-webui.albandrieu.com",
                service="https://open-webui:8080",
                status="healthy",
            ),
        ),
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "name": service.name,
                "url": "https://open-webui.albandrieu.com/",
                "reachable": False,
                "http_status": 0,
                "state": "fail",
                "tls_trusted": None,
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[tunnel],
        cloudflare_stale=True,
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["tunnel_stale"] is True


def test_cloudflare_access_response_does_not_hide_down_tunnel() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnelUrl="https://2fauth.albandrieu.com",
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
        internal_results=[],
        runtime=None,
        tunnels=[tunnel],
    )

    assert rows[0]["state"] == "fail"


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

    async def _runtime():
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
    monkeypatch.setattr(module, "fetch_truenas_runtime", _runtime)
    monkeypatch.setattr(module, "observe_cloudflare_exposure", _cloudflare)
    monkeypatch.setattr(module, "fetch_homelab_topology", _topology)
    monkeypatch.setattr(module, "observe_pfsense_dns_posture", _dns)

    payload = asyncio.run(module.reconcile_homelab_health_payload({"services": []}))

    assert payload["truenas_runtime_reachable"] is False
    assert payload["truenas_runtime_error"] == "You are not allowed to access this resource"


def test_tcp_only_postgresql_dependency_row_is_preserved() -> None:
    service = HomelabService(
        id="postgresql",
        name="PostgreSQL",
        tunnelUrl="postgres://postgres.albandrieu.com:5432/",
        internalHost="172.17.0.24",
        internalPort=5432,
        external=False,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[
            {
                "id": "postgresql",
                "name": "PostgreSQL",
                "host": "172.17.0.24",
                "port": 5432,
                "reachable": True,
                "state": "ok",
            },
        ],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["id"] == "postgresql"
    assert rows[0]["url"] == "postgres://postgres.albandrieu.com:5432/"
    assert rows[0]["internal_state"] == "ok"
    assert rows[0]["state"] == "ok"
