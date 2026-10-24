"""Service-level health evidence policy tests."""

import pytest

from nabla.api.cloudflare_tunnels import CloudflareTunnelIngress, CloudflareTunnelObservation
from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot
from nabla.api.homelab_runtime_models import ObservedContainer
from nabla.api.homelab_service_health import build_reconciled_service_health, reconcile_service_state


def _runtime(*apps: ObservedApp, stale: bool = False) -> TrueNASRuntimeSnapshot:
    return TrueNASRuntimeSnapshot(
        observed_at="2026-09-10T18:00:00Z",
        configured=True,
        reachable=True,
        stale=stale,
        apps=list(apps),
    )


@pytest.mark.parametrize(
    ("direct", "internal", "runtime", "tunnel", "external", "http", "expected"),
    [
        ("ok", None, None, None, True, 200, "ok"),
        ("warn", None, None, None, True, 403, "warn"),
        ("fail", "ok", None, None, True, 0, "warn"),
        ("fail", None, "ok", None, True, 0, "warn"),
        ("fail", None, None, "ok", True, 0, "fail"),
        ("ok", None, None, "fail", True, 200, "warn"),
        ("ok", "ok", None, "fail", True, 200, "warn"),
        (None, "ok", None, None, False, 0, "ok"),
        (None, None, "ok", None, False, 0, "ok"),
        (None, None, "ok", None, True, 0, "warn"),
        (None, None, None, None, True, 0, "unknown"),
    ],
)
def test_service_state_evidence_matrix(
    direct: str | None,
    internal: str | None,
    runtime: str | None,
    tunnel: str | None,
    external: bool,
    http: int,
    expected: str,
) -> None:
    assert (
        reconcile_service_state(
            direct=direct,
            internal=internal,
            runtime=runtime,
            tunnel=tunnel,
            external=external,
            direct_http_status=http,
        )
        == expected
    )


def test_runtime_missing_with_http_200_is_drift_not_outage() -> None:
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
    assert rows[0]["state"] == "warn"


def test_stopped_runtime_is_authoritative_without_fresh_origin() -> None:
    service = HomelabService(name="Open WebUI", external=False)
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=_runtime(ObservedApp(app_id="open-webui", name="Open WebUI", state="STOPPED")),
        tunnels=[],
    )
    assert rows[0]["runtime_state"] == "STOPPED"
    assert rows[0]["state"] == "fail"


def test_stale_runtime_never_claims_missing_app() -> None:
    service = HomelabService(name="Keycloak", external=False)
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=_runtime(stale=True),
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


@pytest.mark.parametrize("tunnel_status", ["healthy", "down", "degraded"])
def test_cloudflare_unconfirmed_warns_without_changing_healthy_origin(tunnel_status: str) -> None:
    service = HomelabService(
        name="n8n",
        tunnelUrl="https://n8n.albandrieu.com",
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": service.service_id,
                "url": "https://n8n.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
            },
        ],
        internal_results=[],
        runtime=None,
        tunnels=[
            CloudflareTunnelObservation(
                tunnel_id="test-tunnel",
                name="test",
                status=tunnel_status,
                ingress=[
                    CloudflareTunnelIngress(
                        tunnel_id="test-tunnel",
                        tunnel_name="test",
                        hostname="n8n.albandrieu.com",
                        service="http://origin:5678",
                    ),
                ],
            ),
        ],
        cloudflare_status_confirmed=False,
        cloudflare_warning="⚠️ Cloudflare global status could not be confirmed: timeout",
    )
    assert rows[0]["state"] == "ok"
    assert rows[0]["cloudflare_status_confirmed"] is False
    assert rows[0]["cloudflare_warning"].startswith("⚠️")


def test_confirmed_down_tunnel_is_not_masked_by_http_403() -> None:
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
    assert rows[0]["tunnel_status"] == "down"
    assert rows[0]["state"] == "fail"


def test_private_garage_admin_uses_lan_health_without_tunnel_downgrade() -> None:
    service = HomelabService(
        id="garage-admin",
        name="Garage Admin API",
        internalHost="172.17.0.24",
        internalPort=3903,
        tunnelUrl="https://garage-admin.albandrieu.com",
        external=False,
    )
    tunnel = CloudflareTunnelObservation(
        tunnel_id="old-route",
        name="legacy",
        status="down",
        ingress=[
            CloudflareTunnelIngress(
                tunnel_id="old-route",
                tunnel_name="legacy",
                hostname="garage-admin.albandrieu.com",
                service="http://garage:3903",
            ),
        ],
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[
            {
                "id": "garage-admin",
                "state": "ok",
                "reachable": True,
                "probe_source": "origin",
                "probe_stale": False,
            },
        ],
        runtime=None,
        tunnels=[tunnel],
    )
    assert rows[0]["state"] == "ok"
    assert rows[0]["internal_state"] == "ok"
    assert rows[0]["exposure_intent"] == "internal"
    assert rows[0]["unexpected_tunnel_route"] is True


def test_stale_direct_application_error_does_not_override_fresh_lan_health() -> None:
    service = HomelabService(
        id="garage-admin",
        name="Garage Admin API",
        internalHost="172.17.0.24",
        internalPort=3903,
        tunnelUrl="https://garage-admin.albandrieu.com",
        external=False,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[
            {
                "id": "garage-admin",
                "url": "https://garage-admin.albandrieu.com/",
                "reachable": True,
                "http_status": 502,
                "state": "fail",
                "tls_trusted": True,
                "application_error": True,
                "probe_stale": True,
            },
        ],
        internal_results=[
            {
                "id": "garage-admin",
                "state": "ok",
                "reachable": True,
                "probe_stale": False,
            },
        ],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["state"] == "ok"
    assert rows[0]["direct_state"] is None
    assert rows[0]["reachable"] is False
    assert rows[0]["http_status"] == 0
    assert rows[0]["tls_trusted"] is None
    assert "application_error" not in rows[0]


def test_stale_internal_garage_evidence_is_not_current_health() -> None:
    service = HomelabService(
        id="garage",
        name="Garage S3 API",
        internalHost="172.17.0.24",
        internalPort=3900,
        external=False,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[
            {
                "id": "garage",
                "state": "ok",
                "reachable": None,
                "probe_source": "memory",
                "probe_stale": True,
            },
        ],
        runtime=None,
        tunnels=[],
    )
    assert rows[0]["state"] == "unknown"
    assert rows[0]["internal_state"] is None
    assert rows[0]["internal_probe_stale"] is True


def _access_blocked_public_row(service_id: str, url: str) -> dict:
    return {
        "id": service_id,
        "url": url,
        "reachable": True,
        "http_status": 302,
        "state": "warn",
        "tls_trusted": True,
        "cloudflare_access_secondary_probe_eligible": True,
        "cloudflare_access_secondary_probe_attempted": True,
        "public_probe_verification": "access_protected_origin_unverified",
        "public_probe_auth_mode": "cloudflare_access_blocked",
        "anonymous_http_status": 302,
        "origin_reached": False,
        "cloudflare_service_token_rejected": False,
    }


@pytest.mark.parametrize(
    ("service_id", "url", "port", "lan_state"),
    [
        ("ittools", "https://ittools.albandrieu.com", 30063, "ok"),
        ("karakeep", "https://karakeep.albandrieu.com", 30147, "fail"),
    ],
)
def test_access_evidence_is_exported_and_never_proves_origin_health(
    service_id: str,
    url: str,
    port: int,
    lan_state: str,
) -> None:
    service = HomelabService(
        id=service_id,
        name=service_id,
        internalHost="172.17.0.24",
        internalPort=port,
        tunnelUrl=url,
        tunnelSecure=True,
        external=True,
    )
    rows = build_reconciled_service_health(
        [service],
        public_results=[_access_blocked_public_row(service_id, f"{url}/")],
        internal_results=[{"id": service_id, "state": lan_state, "reachable": lan_state == "ok"}],
        runtime=None,
        tunnels=[],
    )

    row = rows[0]
    assert row["public_probe_verification"] == "access_protected_origin_unverified"
    assert row["public_probe_auth_mode"] == "cloudflare_access_blocked"
    assert row["cloudflare_access_secondary_probe_eligible"] is True
    assert row["cloudflare_access_secondary_probe_attempted"] is True
    assert row["anonymous_http_status"] == 302
    assert row["origin_reached"] is False
    assert row["internal_state"] == lan_state
    # An Access redirect is edge evidence only: never "ok", even with a healthy LAN origin.
    assert row["state"] == "warn"


def test_true_nas_app_running_does_not_hide_exited_primary_prometheus() -> None:
    service = HomelabService(id="prometheus", name="Prometheus", external=False)
    app = ObservedApp(
        app_id="prometheus",
        name="prometheus",
        state="RUNNING",
        containers=[
            ObservedContainer(service_name="prometheus", state="exited"),
            ObservedContainer(service_name="node-exporter", state="running"),
            ObservedContainer(service_name="alertmanager", state="running"),
        ],
    )
    row = build_reconciled_service_health(
        [service], public_results=[], internal_results=[],
        runtime=_runtime(app), tunnels=[],
    )[0]
    assert row["runtime_state"] == "RUNNING"
    assert row["runtime_primary_container_state"] == "EXITED"
    assert row["runtime_primary_container_issue"] is True
    assert row["state"] == "warn"


def test_exited_init_sidecar_does_not_degrade_running_primary() -> None:
    service = HomelabService(id="gatus", name="Gatus", external=False)
    app = ObservedApp(
        app_id="gatus", name="gatus", state="RUNNING",
        containers=[
            ObservedContainer(service_name="gatus", state="running"),
            ObservedContainer(service_name="migration", state="exited"),
        ],
    )
    row = build_reconciled_service_health(
        [service], public_results=[], internal_results=[],
        runtime=_runtime(app), tunnels=[],
    )[0]
    assert row["runtime_primary_container_state"] == "RUNNING"
    assert row["runtime_primary_container_issue"] is False
    assert row["state"] == "ok"


def test_ambiguous_primary_is_unknown_not_synthetic_success() -> None:
    service = HomelabService(id="prometheus", name="Prometheus", external=False)
    app = ObservedApp(
        app_id="prometheus", name="prometheus", state="RUNNING",
        containers=[
            ObservedContainer(service_name="prometheus", state="running"),
            ObservedContainer(service_name="prometheus", state="exited"),
        ],
    )
    row = build_reconciled_service_health(
        [service], public_results=[], internal_results=[],
        runtime=_runtime(app), tunnels=[],
    )[0]
    assert row["runtime_primary_container_state"] is None
    assert row["runtime_primary_container_issue"] is False


def test_stale_runtime_container_issue_does_not_claim_current_failure() -> None:
    service = HomelabService(id="prometheus", name="Prometheus", external=False)
    app = ObservedApp(
        app_id="prometheus", name="prometheus", state="RUNNING",
        containers=[ObservedContainer(service_name="prometheus", state="exited")],
    )
    row = build_reconciled_service_health(
        [service], public_results=[], internal_results=[],
        runtime=_runtime(app, stale=True), tunnels=[],
    )[0]
    assert row["runtime_primary_container_state"] == "EXITED"
    assert row["runtime_primary_container_issue"] is False
    assert row["state"] == "unknown"
