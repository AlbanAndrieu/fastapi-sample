"""Tests for desired versus observed Cloudflare homelab exposure."""

from fastapi import FastAPI

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)
from nabla.api.health_routes import register_health_routes
from nabla.api.homelab_exposure_audit import build_exposure_audit_payload
from nabla.api.homelab_models import HomelabService


def _remote_tunnel(*hostnames: str) -> CloudflareTunnelObservation:
    return CloudflareTunnelObservation(
        tunnel_id="tunnel-1",
        name="homelab",
        status="healthy",
        config_source="cloudflare",
        ingress=tuple(
            CloudflareTunnelIngress(
                tunnel_id="tunnel-1",
                tunnel_name="homelab",
                hostname=hostname,
                service="http://172.17.0.24:8080",
                status="healthy",
            )
            for hostname in hostnames
        ),
    )


def test_external_service_with_observed_tunnel_matches() -> None:
    service = HomelabService(
        name="Vaultwarden",
        tunnelUrl="https://vaultwarden.albandrieu.com",
        external=True,
    )
    payload = build_exposure_audit_payload(
        [service],
        [_remote_tunnel("vaultwarden.albandrieu.com")],
        configured=True,
    )
    assert payload["status"] == "ok"
    assert payload["findings"][0]["state"] == "MATCH"
    assert payload["findings"][0]["observed_exposed"] is True


def test_non_external_service_with_observed_tunnel_is_security_failure() -> None:
    service = HomelabService(
        name="SABnzbd",
        tunnelUrl="https://sabnzbd.albandrieu.com",
        external=False,
    )
    payload = build_exposure_audit_payload(
        [service],
        [_remote_tunnel("sabnzbd.albandrieu.com")],
        configured=True,
    )
    assert payload["status"] == "fail"
    assert payload["summary"]["unexpectedly_exposed"] == 1
    assert payload["findings"][0]["state"] == "UNEXPECTEDLY_EXPOSED"


def test_missing_external_tunnel_is_reported_without_inventing_exposure() -> None:
    service = HomelabService(
        name="LiteLLM",
        tunnelUrl="https://litellm.albandrieu.com",
        external=True,
    )
    payload = build_exposure_audit_payload([service], [], configured=True)
    assert payload["status"] == "warn"
    assert payload["findings"][0]["state"] == "MISSING_EXPOSURE"
    assert payload["findings"][0]["observed_exposed"] is False


def test_locally_managed_tunnel_makes_absence_unknown() -> None:
    service = HomelabService(
        name="LiteLLM",
        tunnelUrl="https://litellm.albandrieu.com",
        external=True,
    )
    local = CloudflareTunnelObservation(
        tunnel_id="local-1",
        name="local-config",
        status="healthy",
        config_source="local",
    )
    payload = build_exposure_audit_payload([service], [local], configured=True)
    assert payload["status"] == "warn"
    assert payload["authoritative"] is False
    assert payload["has_unknown_local_config"] is True
    assert payload["findings"][0]["state"] == "UNKNOWN"


def test_unmanaged_cloudflare_hostname_is_unexpected_exposure() -> None:
    payload = build_exposure_audit_payload(
        [],
        [_remote_tunnel("shadow.albandrieu.com")],
        configured=True,
    )
    assert payload["status"] == "fail"
    finding = payload["findings"][0]
    assert finding["id"] is None
    assert finding["hostname"] == "shadow.albandrieu.com"
    assert finding["state"] == "UNEXPECTEDLY_EXPOSED"


def test_direct_wan_nonstandard_port_is_not_treated_as_cloudflare_ingress() -> None:
    service = HomelabService(
        name="Home",
        tunnelUrl="https://home.albandrieu.com:10443",
        external=False,
    )
    payload = build_exposure_audit_payload([service], [], configured=True)
    assert payload["status"] == "ok"
    assert payload["findings"] == []


def test_exposure_audit_route_is_registered() -> None:
    app = FastAPI()
    register_health_routes(app)
    assert "/api/homelab/exposure-audit" in {route.path for route in app.routes}
