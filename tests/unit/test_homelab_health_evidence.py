"""Tests for multi-source homelab health reconciliation."""

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)
from nabla.api.homelab_health_evidence import build_reconciled_service_health
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot


def _runtime(*apps: ObservedApp) -> TrueNASRuntimeSnapshot:
    return TrueNASRuntimeSnapshot(
        observed_at="2026-08-26T15:00:00Z",
        configured=True,
        reachable=True,
        apps=list(apps),
    )


def test_private_running_service_is_warning_without_direct_probe() -> None:
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
        internal_results=[],
        runtime=_runtime(ObservedApp(app_id="hello", name="hello", state="RUNNING")),
        tunnels=[],
    )

    assert rows[0]["state"] == "warn"
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
            }
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
            }
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
            }
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
            }
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
            "runtime_reachable": None,
        }
    ]


def test_application_error_remains_failure_despite_positive_runtime() -> None:
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
            }
        ],
        internal_results=[],
        runtime=_runtime(
            ObservedApp(app_id="languagetool", name="LanguageTool", state="RUNNING")
        ),
        tunnels=[],
    )

    assert rows[0]["state"] == "fail"
    assert rows[0]["application_error"] == "Application error"
