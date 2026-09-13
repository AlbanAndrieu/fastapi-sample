"""Contracts for separating service availability from Cloudflare exposure risk."""

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessControlPlaneObservation,
    CloudflareAccessPolicyObservation,
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)
from nabla.api.homelab_exposure import CloudflareExposureSnapshot, enrich_service_exposure
from nabla.api.homelab_models import HomelabService
from nabla.api.sickz_policy import _service_auth_access_result


def _tunnel(hostname: str) -> CloudflareTunnelObservation:
    return CloudflareTunnelObservation(
        tunnel_id="tunnel-1",
        name="nabla-truescale",
        status="healthy",
        config_source="cloudflare",
        ingress=(
            CloudflareTunnelIngress(
                tunnel_id="tunnel-1",
                tunnel_name="nabla-truescale",
                hostname=hostname,
                service="http://172.17.0.24:8080",
                status="healthy",
            ),
        ),
    )


def _access(
    hostname: str,
    *,
    with_policy: bool = True,
) -> CloudflareAccessApplicationObservation:
    policies = (
        CloudflareAccessPolicyObservation(
            policy_id="policy-1",
            name="fastapi-sample-monitor",
            decision="non_identity",
            includes_everyone=False,
        ),
    ) if with_policy else ()
    return CloudflareAccessApplicationObservation(
        app_id="app-1",
        name="service",
        domain=hostname,
        hostname=hostname,
        path="/",
        policies=policies,
    )


def _control_plane(
    *,
    policy_count: int = 1,
    policy_app_count: int = 1,
    token_count: int = 1,
    token_enabled_count: int = 1,
    configured_token_present: bool = True,
) -> CloudflareAccessControlPlaneObservation:
    return CloudflareAccessControlPlaneObservation(
        reusable_policy_count=policy_count,
        reusable_policy_total_count=policy_count,
        reusable_policy_app_count=policy_app_count,
        service_token_count=token_count,
        service_token_total_count=token_count,
        service_token_enabled_count=token_enabled_count,
        configured_service_token_present=configured_token_present,
    )


def _row(service: HomelabService) -> dict[str, object]:
    return {
        "id": service.service_id,
        "name": service.name,
        "url": service.effective_endpoint_url,
        "reachable": True,
        "http_status": 200,
        "state": "ok",
        "local_state": "ok",
        "effective_state": "ok",
    }


def _protected_service(
    hostname: str = "openwebui.albandrieu.com",
) -> HomelabService:
    return HomelabService(
        name="Open WebUI",
        tunnelUrl=f"https://{hostname}",
        tunnelSecure=True,
        cloudflareAccessRequired=True,
        external=True,
    )


def test_protected_cloudflare_service_can_be_operational_without_risk() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(_access("openwebui.albandrieu.com"),),
        access_control_plane=_control_plane(),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["state"] == "ok"
    assert row["risk_state"] == "none"
    assert row["risk_reasons"] == []
    assert row["exposure"]["state"] == "match"


def test_missing_access_application_is_at_risk_without_marking_service_down() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_control_plane=_control_plane(),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["state"] == "ok"
    assert row["local_state"] == "ok"
    assert row["risk_state"] == "at_risk"
    assert any("no matching Access application" in reason for reason in row["risk_reasons"])


def test_access_application_without_policy_is_at_risk() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(
            _access("openwebui.albandrieu.com", with_policy=False),
        ),
        access_control_plane=_control_plane(),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["risk_state"] == "at_risk"
    assert any("contains no policy" in reason for reason in row["risk_reasons"])


def test_missing_project_policy_and_service_token_are_at_risk() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(_access("openwebui.albandrieu.com"),),
        access_control_plane=_control_plane(
            policy_count=0,
            policy_app_count=0,
            token_count=0,
            token_enabled_count=0,
            configured_token_present=False,
        ),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["risk_state"] == "at_risk"
    assert any("reusable Access policy is missing" in reason for reason in row["risk_reasons"])
    assert any("Service Token is missing" in reason for reason in row["risk_reasons"])
    assert any("does not match" in reason for reason in row["risk_reasons"])


def test_disabled_or_unmatched_project_service_token_is_at_risk() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(_access("openwebui.albandrieu.com"),),
        access_control_plane=_control_plane(
            token_count=1,
            token_enabled_count=0,
            configured_token_present=False,
        ),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["risk_state"] == "at_risk"
    assert any("no token is enabled" in reason for reason in row["risk_reasons"])
    assert any("does not match" in reason for reason in row["risk_reasons"])


def test_direct_external_int_hostname_is_at_risk() -> None:
    service = HomelabService(
        name="Garage S3",
        tunnelUrl="https://s3.int.albandrieu.com",
        tunnelSecure=False,
        cloudflareAccessRequired=False,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(configured=True)

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["state"] == "ok"
    assert row["risk_state"] == "at_risk"
    assert any("*.int.albandrieu.com" in reason for reason in row["risk_reasons"])
    assert any("directly exposed" in reason for reason in row["risk_reasons"])


def test_cloudflare_tunnel_with_access_disabled_is_at_risk() -> None:
    service = HomelabService(
        name="Public dashboard",
        tunnelUrl="https://dashboard.albandrieu.com",
        tunnelSecure=True,
        cloudflareAccessRequired=False,
        external=True,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("dashboard.albandrieu.com"),),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["risk_state"] == "at_risk"
    assert any("Access is disabled" in reason for reason in row["risk_reasons"])
    assert any("anonymous exposure" in reason for reason in row["risk_reasons"])


def test_private_service_with_observed_tunnel_is_at_risk() -> None:
    service = HomelabService(
        name="Private service",
        tunnelUrl="https://private.albandrieu.com",
        tunnelSecure=True,
        external=False,
    )
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("private.albandrieu.com"),),
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["state"] == "ok"
    assert row["risk_state"] == "at_risk"
    assert row["exposure"]["state"] == "mismatch"
    assert any("not declared external" in reason for reason in row["risk_reasons"])


def test_provider_timeout_or_stale_inventory_is_unknown_not_at_risk() -> None:
    service = _protected_service()
    snapshot = CloudflareExposureSnapshot(
        configured=True,
        tunnels=(_tunnel("openwebui.albandrieu.com"),),
        access_applications=(_access("openwebui.albandrieu.com"),),
        access_control_plane=_control_plane(),
        stale=True,
        refresh_error="TimeoutError",
    )

    row = enrich_service_exposure([_row(service)], [service], snapshot)[0]

    assert row["state"] == "ok"
    assert row["risk_state"] == "unknown"
    assert row["risk_state"] != "at_risk"
    assert any("could not be confirmed" in reason for reason in row["risk_reasons"])


def test_service_auth_failure_remains_policy_failure_for_at_risk_projection() -> None:
    state, detail = _service_auth_access_result(
        blocked=True,
        attempted=True,
        passed=False,
        observed_policy=True,
    )

    assert state == "fail"
    assert "Service Token did not pass Access" in detail
    assert "Verify the Service Auth policy and token selectors" in detail
