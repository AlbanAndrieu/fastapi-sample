"""Tests for sanitized declared-versus-observed edge exposure evidence."""

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessPolicyObservation,
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)
from nabla.api.homelab_exposure import CloudflareExposureSnapshot, enrich_service_exposure
from nabla.api.homelab_models import HomelabService


def _tunnel(hostname: str) -> CloudflareTunnelObservation:
    return CloudflareTunnelObservation(
        tunnel_id="tunnel-1",
        name="homelab",
        status="healthy",
        config_source="cloudflare",
        ingress=(
            CloudflareTunnelIngress(
                tunnel_id="tunnel-1",
                tunnel_name="homelab",
                hostname=hostname,
                service="http://service:8080",
                status="healthy",
            ),
        ),
    )


def _access(hostname: str, *, public: bool = False) -> CloudflareAccessApplicationObservation:
    return CloudflareAccessApplicationObservation(
        app_id="access-1",
        name="service",
        domain=hostname,
        hostname=hostname,
        path="/",
        policies=(
            CloudflareAccessPolicyObservation(
                policy_id="policy-1",
                name="policy",
                decision="bypass" if public else "allow",
                includes_everyone=public,
            ),
        ),
    )


def _row(service: HomelabService) -> dict[str, object]:
    return {
        "id": service.service_id,
        "name": service.name,
        "url": service.effective_endpoint_url,
        "reachable": True,
        "http_status": 200,
        "state": "ok",
    }


def test_cloudflare_tunnel_and_protected_access_match_declaration() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://openwebui.albandrieu.com",
        tunnelSecure=True,
        cloudflareAccessRequired=True,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(_access("openwebui.albandrieu.com"),),
    )

    result = enrich_service_exposure([_row(service)], [service], snapshot)[0]["exposure"]

    assert result["state"] == "match"
    assert result["declared"]["edge_mode"] == "cloudflare"
    assert result["observed"]["cloudflare_tunnel_observed"] is True
    assert result["observed"]["cloudflare_access_observed"] is True
    assert result["observed"]["cloudflare_access_public"] is False


def test_broad_cloudflare_access_bypass_is_mismatch() -> None:
    service = HomelabService(
        name="n8n",
        tunnelUrl="https://n8n.albandrieu.com",
        tunnelSecure=True,
        cloudflareAccessRequired=True,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("n8n.albandrieu.com"),),
        access_applications=(_access("n8n.albandrieu.com", public=True),),
    )

    result = enrich_service_exposure([_row(service)], [service], snapshot)[0]["exposure"]

    assert result["state"] == "mismatch"
    assert result["observed"]["cloudflare_access_public"] is True
    assert result["observed"]["cloudflare_access_public_scope"] == "host"
    assert any("public/bypass" in reason for reason in result["reasons"])


def test_direct_service_with_observed_tunnel_is_mismatch() -> None:
    service = HomelabService(
        name="TrueNAS",
        tunnelUrl="https://truenas.albandrieu.com:7000",
        tunnelSecure=False,
        cloudflareAccessRequired=False,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("truenas.albandrieu.com"),),
    )

    result = enrich_service_exposure([_row(service)], [service], snapshot)[0]["exposure"]

    assert result["state"] == "mismatch"
    assert result["declared"]["edge_mode"] == "direct"


def test_access_observer_failure_is_incomplete_not_mismatch() -> None:
    service = HomelabService(
        name="Open WebUI",
        tunnelUrl="https://openwebui.albandrieu.com",
        tunnelSecure=True,
        cloudflareAccessRequired=True,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_error="PermissionDenied",
    )

    result = enrich_service_exposure([_row(service)], [service], snapshot)[0]["exposure"]

    assert result["state"] == "incomplete"
    assert result["observed"]["cloudflare_access_observed"] is False
    assert any("observation failed" in reason for reason in result["reasons"])
