"""Regression tests for non-degrading Cloudflare uncertainty."""

import asyncio

import httpx
import pytest

from nabla.api import component_health, health_board, homelab_catalog, homelab_exposure, platform_health


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
    assert result["state"] == "unknown"
    assert result["status_confirmed"] is False
    assert result["warning"].startswith("⚠️ Cloudflare global status could not be confirmed")


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
    monkeypatch.setattr(homelab_exposure, "_CLOUDFLARE_OBSERVER_TIMEOUT_SEC", 0.01)

    async def slow_to_thread(*_args, **_kwargs):
        await asyncio.sleep(1)
        return []

    monkeypatch.setattr(homelab_exposure.asyncio, "to_thread", slow_to_thread)
    payload = await homelab_exposure._observe_cloudflare_exposure_origin()

    assert payload["tunnel_error"] == "TimeoutError"
    assert payload["access_error"] == "TimeoutError"


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
        )
    ]
