"""Unit tests for sickz exposure-policy reconciliation."""

from nabla.api.homelab_models import HomelabService
from nabla.api.sickz_policy import _classify_service


def _check(*, reachable: bool, tls_trusted: bool | None = True, status: int = 200) -> dict:
    return {
        "reachable": reachable,
        "tls_trusted": tls_trusted,
        "http_status": status,
    }


def test_private_service_reachable_is_policy_failure() -> None:
    service = HomelabService(
        name="Bichon",
        tunnel_url="https://bichon.albandrieu.com",
        tunnel_secure=True,
        external=False,
    )

    state, detail = _classify_service(
        service,
        _check(reachable=True),
        tunnel_evidence=None,
        observer_configured=True,
        observer_error=None,
        http_evidence={"cloudflare_http_evidence": False},
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
        tunnel_secure=True,
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


def test_secure_external_service_with_tunnel_and_tls_is_ok() -> None:
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
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "ok"
    assert "observed Cloudflare Tunnel ingress" in detail


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
        http_evidence={"cloudflare_http_evidence": False},
    )

    assert state == "fail"
    assert "without any observed Cloudflare" in detail


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
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "fail"
    assert "TLS certificate is not trusted" in detail


def test_cloudflare_http_evidence_degrades_when_observer_fails() -> None:
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
        http_evidence={"cloudflare_http_evidence": True},
    )

    assert state == "warn"
    assert "observer failed" in detail


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
