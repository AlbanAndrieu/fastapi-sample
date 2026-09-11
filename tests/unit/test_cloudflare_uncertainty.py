"""Regression tests for non-degrading Cloudflare uncertainty."""

import asyncio

import httpx
import pytest

from nabla.api import (
    cloudflare_exposure_observer,
    component_health,
    health_board,
    homelab_catalog,
    platform_health,
)
from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessPolicyObservation,
    CloudflareTunnelIngress,
    CloudflareTunnelObservation,
)


@pytest.mark.asyncio
async def test_cloudflare_transport_failure_is_unknown_warning(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Cloudflare connect timeout", request=request)

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    result = await platform_health.check_cloudflare_tunnels()

    assert result["reachable"] is None
    assert result["degraded"] is False
    assert result["state"] == "unknown"
    assert result["status_confirmed"] is False
    assert result["warning"].startswith(
        "⚠️ Cloudflare global status could not be confirmed",
    )


@pytest.mark.asyncio
async def test_cloudflare_http_error_is_unconfirmed_not_down(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            request=request,
            json={"success": False, "errors": [{"code": 1000, "message": "temporary"}]},
        )

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    result = await platform_health.check_cloudflare_tunnels()

    assert result["reachable"] is None
    assert result["degraded"] is False
    assert result["status_confirmed"] is False
    assert result["http_status"] == 503


@pytest.mark.asyncio
async def test_cloudflare_empty_inventory_is_unknown_not_down(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"success": True, "result": []})

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    result = await platform_health.check_cloudflare_tunnels()

    assert result["reachable"] is None
    assert result["degraded"] is False
    assert result["error_kind"] == "empty_inventory"
    assert result["status_confirmed"] is False


def test_unconfirmed_cloudflare_does_not_degrade_platform() -> None:
    components = {
        "postgres": {"reachable": True},
        "redis": {"reachable": True},
        "supabase": {"reachable": True},
        "truenas": {"reachable": True, "state": "ok", "tls_trusted": True},
        "cloudflare": {
            "reachable": None,
            "state": "unknown",
            "status_confirmed": False,
            "stale": True,
        },
        "pfsense": {"reachable": True},
    }
    assert component_health.component_status(components) == "healthy"


def test_cloudflare_optional_deadline_is_non_degrading_unknown() -> None:
    result = health_board._cloudflare_unconfirmed_check(
        error="optional diagnostic enrichment deadline exceeded",
        error_kind="deadline",
        timed_out=True,
    )
    assert result["reachable"] is None
    assert result["status_confirmed"] is False
    assert result["timed_out"] is True


@pytest.mark.asyncio
async def test_cloudflare_exposure_observers_have_independent_timeout(monkeypatch) -> None:
    monkeypatch.setattr(cloudflare_exposure_observer, "_OBSERVER_TIMEOUT_SEC", 0.01)

    async def slow_to_thread(*_args, **_kwargs):
        await asyncio.sleep(1)
        return []

    monkeypatch.setattr(cloudflare_exposure_observer.asyncio, "to_thread", slow_to_thread)
    payload = await cloudflare_exposure_observer._origin()

    assert payload["tunnel_error"] == "TimeoutError"
    assert payload["access_error"] == "TimeoutError"


def test_empty_exposure_summary_is_warning_not_degraded() -> None:
    snapshot = cloudflare_exposure_observer.CloudflareExposureSnapshot(configured=True)
    summary = snapshot.summary()

    assert summary["status_confirmed"] is False
    assert summary["degraded"] is False
    assert summary["effective_state"] == "warn"
    assert summary["warning"].startswith("⚠️")


def test_exposure_summary_reports_local_vs_dashboard_managed_tunnels() -> None:
    tunnel = cloudflare_exposure_observer.CloudflareTunnelObservation
    snapshot = cloudflare_exposure_observer.CloudflareExposureSnapshot(
        configured=True,
        tunnels=(
            tunnel(tunnel_id="local", name="local", config_source="local"),
            tunnel(tunnel_id="remote", name="remote", config_source="cloudflare"),
            tunnel(tunnel_id="unknown", name="unknown"),
        ),
    )

    summary = snapshot.summary()

    assert summary["local_managed_tunnels"] == 1
    assert summary["cloudflare_managed_tunnels"] == 1
    assert summary["unknown_management_tunnels"] == 1
    assert summary["tunnel_config_sources"] == ["cloudflare", "local", "unknown"]


def test_exposure_summary_includes_sanitized_routes_and_access_policies() -> None:
    credential_like_origin = (
        "http://"
        + "fixture-user"
        + ":"
        + "fixture-password"
        + "@"
        + "172.17.0.24:8091/api?token=fixture-token"
    )
    snapshot = cloudflare_exposure_observer.CloudflareExposureSnapshot(
        configured=True,
        tunnels=(
            CloudflareTunnelObservation(
                tunnel_id="tunnel-id",
                name="homelab",
                status="healthy",
                config_source="cloudflare",
                ingress=(
                    CloudflareTunnelIngress(
                        tunnel_id="tunnel-id",
                        tunnel_name="homelab",
                        hostname="sample.albandrieu.com",
                        service=credential_like_origin,
                        status="healthy",
                    ),
                ),
            ),
        ),
        access_applications=(
            CloudflareAccessApplicationObservation(
                app_id="app-id",
                name="FastAPI Sample",
                domain="sample.albandrieu.com",
                hostname="sample.albandrieu.com",
                policies=(
                    CloudflareAccessPolicyObservation(
                        policy_id="policy-id",
                        name="Service Token",
                        decision="non_identity",
                    ),
                ),
            ),
        ),
    )

    summary = snapshot.summary()

    assert summary["tunnels"] == [
        {
            "name": "homelab",
            "status": "healthy",
            "management": "cloudflare",
            "ingress_count": 1,
            "ingress_visibility": "remote_api",
            "ingress": [
                {
                    "hostname": "sample.albandrieu.com",
                    "service": "http://172.17.0.24:8091/api",
                    "status": "healthy",
                },
            ],
        },
    ]
    assert summary["access_applications"] == [
        {
            "name": "FastAPI Sample",
            "domain": "sample.albandrieu.com",
            "path": "/",
            "policy_count": 1,
            "policies": [
                {
                    "name": "Service Token",
                    "decision": "non_identity",
                    "includes_everyone": False,
                },
            ],
        },
    ]
    serialized = str(summary)
    assert "fixture-password" not in serialized
    assert "fixture-token" not in serialized
    assert "policy-id" not in serialized
    assert "app-id" not in serialized
    assert "tunnel-id" not in serialized


@pytest.mark.asyncio
async def test_legacy_healthz_homelab_rows_only_probe_primary_truenas(monkeypatch) -> None:
    async def should_not_fetch_services():
        raise AssertionError("global /healthz must not enumerate homelab services")

    monkeypatch.setattr(homelab_catalog, "fetch_homelab_services", should_not_fetch_services)
    rows = await homelab_catalog.homelab_healthz_probe_rows()

    assert rows == [
        (
            "albandrieu_truenas",
            "https://truenas.albandrieu.com:7000/",
            "TrueNAS HTTPS",
            None,
        ),
    ]
