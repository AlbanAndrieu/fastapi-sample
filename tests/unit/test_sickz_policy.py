"""Unit tests for sickz exposure-policy reconciliation."""

import httpx
import pytest

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessPolicyObservation,
)
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot
from nabla.api.sickz_policy import (
    _ANONYMOUS_EDGE_HEADERS,
    _access_by_hostname,
    _access_policy_result,
    _classify_service,
    _probe_http_edge_evidence,
    _response_contains_cloudflare_default_deny,
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
        ),
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


@pytest.mark.asyncio
async def test_pfsense_admin_is_not_reprobed_as_cloudflare_edge() -> None:
    evidence = await _probe_http_edge_evidence("https://home.albandrieu.com:10443/")

    assert evidence["cloudflare_http_evidence"] is False
    assert evidence["cloudflare_access_signal"] is False
    assert evidence["http_evidence_skipped"] is True
    assert "not a Cloudflare edge target" in evidence["http_evidence_skip_reason"]


def test_cloudflare_default_deny_body_is_detected() -> None:
    response = httpx.Response(
        403,
        headers={"content-type": "text/html; charset=utf-8"},
        text=("<html><h1>This resource is blocked by this account's <strong>Default-Deny</strong>&nbsp;policy.</h1></html>"),
    )

    assert _response_contains_cloudflare_default_deny(response) is True


def test_access_inventory_exposes_zero_policy_application() -> None:
    apps = [
        CloudflareAccessApplicationObservation(
            app_id="app-uptime",
            name="Uptime Kuma",
            domain="uptime-kuma.albandrieu.com",
            hostname="uptime-kuma.albandrieu.com",
            policies=(),
        ),
    ]

    access = _access_by_hostname(apps)["uptime-kuma.albandrieu.com"]

    assert access["cloudflare_access_application_count"] == 1
    assert access["cloudflare_access_policy_count"] == 0
    assert access["cloudflare_access_policy_names"] == []


def test_default_deny_without_access_application_reports_probable_missing_policy() -> None:
    state, detail = _access_policy_result(
        access_required=True,
        access_evidence=None,
        access_observer_error=None,
        http_evidence={
            "cloudflare_http_evidence": True,
            "cloudflare_default_deny": True,
        },
    )

    assert state == "fail"
    assert "Default-Deny" in detail
    assert "probably missing" in detail


def test_default_deny_with_access_application_but_no_policy_is_failure() -> None:
    state, detail = _access_policy_result(
        access_required=True,
        access_evidence={
            "cloudflare_access_observed": True,
            "cloudflare_access_policy_count": 0,
            "cloudflare_access_public_scope": None,
        },
        access_observer_error=None,
        http_evidence={
            "cloudflare_http_evidence": True,
            "cloudflare_default_deny": True,
        },
    )

    assert state == "fail"
    assert "contains no policy" in detail


def test_default_deny_with_existing_access_policy_is_warning() -> None:
    state, detail = _access_policy_result(
        access_required=True,
        access_evidence={
            "cloudflare_access_observed": True,
            "cloudflare_access_policy_count": 1,
            "cloudflare_access_public_scope": None,
        },
        access_observer_error=None,
        http_evidence={
            "cloudflare_http_evidence": True,
            "cloudflare_default_deny": True,
        },
    )

    assert state == "warn"
    assert "Verify policy selectors" in detail


def test_cloudflare_edge_probe_contract_is_anonymous() -> None:
    assert _ANONYMOUS_EDGE_HEADERS == {
        "User-Agent": "nabla-sickz-policy-probe/1.0",
    }
    lowered = {key.casefold() for key in _ANONYMOUS_EDGE_HEADERS}
    assert "cf-access-client-id" not in lowered
    assert "cf-access-client-secret" not in lowered


@pytest.mark.asyncio
async def test_cloudflare_service_token_retries_after_default_deny(monkeypatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "client-id-test")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "client-secret-test")
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {key.casefold(): value for key, value in request.headers.items()}
        seen_headers.append(headers)
        if "cf-access-client-id" not in headers:
            return httpx.Response(
                403,
                headers={"cf-ray": "test-ray", "content-type": "text/html"},
                text="This resource is blocked by this account's Default-Deny policy.",
            )
        return httpx.Response(
            200,
            headers={"cf-ray": "test-ray-2", "content-type": "text/html"},
            text="<html>origin reached</html>",
        )

    evidence = await _probe_http_edge_evidence(
        "https://uptime-kuma.albandrieu.com/",
        transport=httpx.MockTransport(handler),
    )

    assert len(seen_headers) == 2
    assert "cf-access-client-id" not in seen_headers[0]
    assert "cf-access-client-secret" not in seen_headers[0]
    assert seen_headers[1]["cf-access-client-id"] == "client-id-test"
    assert seen_headers[1]["cf-access-client-secret"] == "client-secret-test"
    assert evidence["http_probe_auth_mode"] == "anonymous"
    assert evidence["cloudflare_default_deny"] is True
    assert evidence["cloudflare_service_token_configured"] is True
    assert evidence["cloudflare_service_token_attempted"] is True
    assert evidence["cloudflare_service_token_access_passed"] is True
    assert evidence["cloudflare_service_token_http_status"] == 200
    assert "client-secret-test" not in repr(evidence)


@pytest.mark.asyncio
async def test_cloudflare_service_token_is_never_sent_to_untrusted_host(monkeypatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "client-id-test")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "client-secret-test")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            403,
            headers={"cf-ray": "test-ray", "content-type": "text/html"},
            text="This resource is blocked by this account's Default-Deny policy.",
        )

    evidence = await _probe_http_edge_evidence(
        "https://example.test/",
        transport=httpx.MockTransport(handler),
    )

    assert calls == 1
    assert evidence["cloudflare_service_token_attempted"] is False
    assert evidence["cloudflare_service_token_skip_reason"] == "untrusted_target"


def test_access_policy_accepts_service_token_after_anonymous_block() -> None:
    state, detail = _access_policy_result(
        access_required=True,
        access_evidence=None,
        access_observer_error=None,
        http_evidence={
            "cloudflare_http_evidence": True,
            "cloudflare_default_deny": True,
            "cloudflare_service_token_attempted": True,
            "cloudflare_service_token_access_passed": True,
        },
    )

    assert state == "ok"
    assert "Service Token passes" in detail


def test_access_policy_reports_service_token_denial_after_anonymous_block() -> None:
    state, detail = _access_policy_result(
        access_required=True,
        access_evidence=None,
        access_observer_error=None,
        http_evidence={
            "cloudflare_http_evidence": True,
            "cloudflare_access_signal": True,
            "cloudflare_service_token_attempted": True,
            "cloudflare_service_token_access_passed": False,
        },
    )

    assert state == "fail"
    assert "Service Token did not pass" in detail
