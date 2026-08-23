"""Tests for optional platform API health probes."""

import httpx
import pytest

from nabla.api import platform_health


@pytest.mark.asyncio
async def test_cloudflare_check_is_skipped_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    result = await platform_health.check_cloudflare_tunnels()

    assert result["skipped"] is True
    assert result["reachable"] is None


@pytest.mark.asyncio
async def test_cloudflare_check_reports_unhealthy_tunnel(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(
            200,
            request=request,
            json={
                "success": True,
                "result": [
                    {"name": "homelab", "status": "healthy"},
                    {"name": "backup", "status": "down"},
                ],
            },
        )

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await platform_health.check_cloudflare_tunnels()

    assert result["api_reachable"] is True
    assert result["reachable"] is False
    assert result["healthy_tunnels"] == 1
    assert result["unhealthy_tunnels"] == 1


@pytest.mark.asyncio
async def test_pfsense_check_is_skipped_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("PFSENSE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_API_KEY", raising=False)

    result = await platform_health.check_pfsense_api()

    assert result["skipped"] is True
    assert result["reachable"] is None


@pytest.mark.asyncio
async def test_pfsense_check_uses_api_key_and_status_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_API_KEY", "key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/status/system"
        assert request.headers["X-API-Key"] == "key"
        return httpx.Response(200, request=request, json={"code": 200, "status": "ok"})

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is True
    assert result["http_status"] == 200
    assert result["probe"] == "pfsense_rest_api_v2"


def test_select_homelab_health_checks_keeps_core_infra_and_platforms() -> None:
    payload = {
        "checks": {
            "postgres": {"reachable": True},
            "redis": {"reachable": True},
            "supabase": {"reachable": True},
            "albandrieu_truenas": {"reachable": False},
            "albandrieu_nexus": {"reachable": True},
            "cloudflare": {"reachable": True},
            "pfsense": {"reachable": None, "skipped": True},
            "litellm": {"reachable": True},
        }
    }

    selected = platform_health.select_homelab_health_checks(payload)

    assert list(selected) == [
        "postgres",
        "redis",
        "supabase",
        "albandrieu_truenas",
        "albandrieu_nexus",
        "cloudflare",
        "pfsense",
    ]
    assert "litellm" not in selected
