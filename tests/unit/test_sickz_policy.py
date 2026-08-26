"""Unit tests for sickz exposure-policy reconciliation."""

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessPolicyObservation,
)
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot
from nabla.api.sickz_policy import (
    _access_by_hostname,
    _classify_service,
    _runtime_evidence,
)


def _check(*, reachable: bool, tls_trusted: bool | None = True, status: int = 200) -> dict:
    return {
        "reachable": reachable,
        "tls_trusted": tls_trusted,
        "http_status": status,
    }


def _protected_access() -> dict:
    return {
        "cloudflare_access_observed": True,
        "cloudflare_access_public": False,
        "cloudflare_access_public_scope": None,
    }


def test_private_service_reachable_is_policy_failure() -> None:
    service = HomelabService(
        name="Bichon",
        tunnel_url="https://bichon.albandrieu.com",
        tunnel_secure=False,
        external=False,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, status=502),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "external=false" in detail


def test_private_service_unreachable_is_policy_ok() -> None:
    service = HomelabService(
        name="ClickHouse",
        tunnel_url="https://clickhouse.albandrieu.com",
        tunnel_secure=True,
        external=False,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=False),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "ok"
    assert "not reachable" in detail


def test_private_service_with_cloudflare_ingress_is_policy_failure() -> None:
    service = HomelabService(
        name="Bichon",
        tunnel_url="https://bichon.albandrieu.com",
        tunnel_secure=False,
        external=False,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=False),
        tunnel_evidence={
            "cloudflare_tunnel_observed": True,
            "cloudflare_tunnel_status": "HEALTHY",
        },
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "Cloudflare Tunnel ingress exists" in detail


def test_private_service_with_access_application_is_policy_failure() -> None:
    service = HomelabService(
        name="Bichon",
        tunnel_url="https://bichon.albandrieu.com",
        tunnel_secure=False,
        external=False,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=False),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        access_evidence=_protected_access(),
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "Cloudflare Access application exists" in detail


def test_secure_external_service_with_tunnel_tls_and_access_is_ok() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnel_url="https://2fauth.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence={
            "cloudflare_tunnel_observed": True,
            "cloudflare_tunnel_status": "HEALTHY",
        },
        observer_configured=True,
        observer_error=None,
        access_evidence=_protected_access(),
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "ok"
    assert "Cloudflare Tunnel ingress is observed" in detail
    assert "Access application/policies are observed" in detail


def test_secure_external_service_without_cloudflare_evidence_fails() -> None:
    service = HomelabService(
        name="2FAuth",
        tunnel_url="https://2fauth.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        access_evidence=_protected_access(),
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "fail"
    assert "no observed Cloudflare Tunnel/edge evidence" in detail


def test_secure_external_service_with_invalid_tls_fails_even_with_tunnel() -> None:
    service = HomelabService(
        name="Vaultwarden",
        tunnel_url="https://vaultwarden.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=False),
        tunnel_evidence={
            "cloudflare_tunnel_observed": True,
            "cloudflare_tunnel_status": "HEALTHY",
        },
        observer_configured=True,
        observer_error=None,
        access_evidence=_protected_access(),
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "TLS certificate is not trusted" in detail


def test_cloudflare_http_evidence_degrades_when_observers_fail() -> None:
    service = HomelabService(
        name="IT Tools",
        tunnel_url="https://ittools.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error="ConnectError",
        access_observer_error="PermissionDenied",
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "warn"
    assert "observer failed" in detail
    assert "Access policy could not be inspected" in detail


def test_direct_int_external_service_is_always_warning_when_reachable() -> None:
    service = HomelabService(
        name="Garage",
        tunnel_url="https://garage.int.albandrieu.com",
        tunnel_secure=False,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "warn"
    assert "⚠️" in detail
    assert "direct-Traefik exception" in detail
    assert "reachable as declared" in detail


def test_direct_int_external_service_stays_warning_when_probe_is_unreachable() -> None:
    service = HomelabService(
        name="Garage",
        tunnel_url="https://garage.int.albandrieu.com",
        tunnel_secure=False,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=False, tls_trusted=None),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "warn"
    assert "could not currently reach" in detail


def test_direct_int_external_service_with_invalid_tls_is_failure() -> None:
    service = HomelabService(
        name="Garage",
        tunnel_url="https://garage.int.albandrieu.com",
        tunnel_secure=False,
        external=True,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=False),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "fail"
    assert "TLS certificate is not trusted" in detail


def test_n8n_broad_access_bypass_is_red_security_exception() -> None:
    """A tunnel can be healthy while Access is intentionally bypassed for everyone.

    This models the historical n8n/Slack webhook workaround. A host-wide bypass must
    stay red so the health board reminds us to narrow the public exception to the
    webhook path or replace it with Cloudflare Service Auth.
    """
    service = HomelabService(
        name="n8n",
        tunnel_url="https://n8n.albandrieu.com",
        tunnel_secure=True,
        external=True,
        cloudflare_access_required=True,
    )
    access = {
        "cloudflare_access_observed": True,
        "cloudflare_access_public": True,
        "cloudflare_access_public_scope": "host",
        "cloudflare_access_public_policies": ["Public Slack webhook workaround"],
    }

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence={
            "cloudflare_tunnel_observed": True,
            "cloudflare_tunnel_status": "HEALTHY",
        },
        observer_configured=True,
        observer_error=None,
        access_evidence=access,
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "⚠️" in detail
    assert "whole hostname" in detail
    assert "check the cloudflare access policy" in detail.lower()


def test_path_scoped_webhook_bypass_is_warning_not_full_host_failure() -> None:
    service = HomelabService(
        name="n8n",
        tunnel_url="https://n8n.albandrieu.com",
        tunnel_secure=True,
        external=True,
    )
    apps = [
        CloudflareAccessApplicationObservation(
            app_id="app-webhook",
            name="n8n webhook",
            domain="n8n.albandrieu.com/webhook/*",
            hostname="n8n.albandrieu.com",
            path="/webhook/*",
            policies=(
                CloudflareAccessPolicyObservation(
                    policy_id="bypass",
                    name="Webhook bypass",
                    decision="bypass",
                    includes_everyone=True,
                ),
            ),
        )
    ]
    access = _access_by_hostname(apps)["n8n.albandrieu.com"]

    state, detail = _classify_service(
        service,
        _check(reachable=True, tls_trusted=True),
        tunnel_evidence={
            "cloudflare_tunnel_observed": True,
            "cloudflare_tunnel_status": "HEALTHY",
        },
        observer_configured=True,
        observer_error=None,
        access_evidence=access,
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "warn"
    assert "path-scoped public bypass" in detail
    assert "/webhook/*" in detail


def test_bichon_crashed_runtime_and_bad_gateway_get_skull_evidence() -> None:
    service = HomelabService(
        name="Bichon",
        tunnel_url="https://bichon.albandrieu.com",
        tunnel_secure=False,
        external=False,
    )
    runtime = TrueNASRuntimeSnapshot(
        observed_at="2026-08-26T17:00:00Z",
        configured=True,
        reachable=True,
        apps=[ObservedApp(app_id="bichon", name="bichon", state="CRASHED")],
    )

    evidence = _runtime_evidence(service, runtime, 502)

    assert evidence["runtime_failed"] is True
    assert evidence["failure_icon"] == "skull"
    assert evidence["icon_src"].endswith("/1f480.svg")
    assert "HTTP 502" in evidence["failure_detail"]
    assert "CRASHED" in evidence["failure_detail"]
