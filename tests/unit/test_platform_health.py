"""Tests for optional platform API health probes."""

import httpx
import pytest

from nabla.api import external_probe_cache, platform_health


def _expire_current_value(key: str) -> None:
    envelope, stored_at = external_probe_cache._l1[key]
    envelope["current"]["fetched_at"] = 0.0
    external_probe_cache._l1[key] = (envelope, stored_at)


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
async def test_cloudflare_404_reports_account_scope_diagnostic(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "wrong-account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            request=request,
            json={
                "success": False,
                "errors": [{"code": 7003, "message": "Could not route to account"}],
            },
        )

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await platform_health.check_cloudflare_tunnels()

    assert result["reachable"] is False
    assert result["api_reachable"] is True
    assert result["http_status"] == 404
    assert "CLOUDFLARE_ACCOUNT_ID" in result["error"]


@pytest.mark.asyncio
async def test_pfsense_check_is_skipped_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("PFSENSE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_API_KEY", raising=False)
    monkeypatch.delenv("PFSENSE_POSTURE_API_URL", raising=False)
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)

    result = await platform_health.check_pfsense_api()

    assert result["skipped"] is True
    assert result["reachable"] is None


@pytest.mark.asyncio
async def test_pfsense_check_rejects_plain_http_api_key_transport(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "http://172.17.0.1")
    monkeypatch.setenv("PFSENSE_API_KEY", "key")
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is False
    assert "must use HTTPS" in result["error"]


@pytest.mark.asyncio
async def test_pfsense_check_uses_api_key_and_lightweight_version_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_API_KEY", "key")
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/system/version"
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
    assert result["path"] == "/api/v2/system/version"
    assert result["credential_mode"] == "legacy_shared"
    assert "/api/v2/status/system" not in result["url"]


@pytest.mark.asyncio
async def test_pfsense_check_prefers_dedicated_posture_key(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_API_KEY", "narrow-snort-key")
    monkeypatch.setenv("PFSENSE_POSTURE_API_KEY", "posture-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/system/version"
        assert request.headers["X-API-Key"] == "posture-key"
        return httpx.Response(200, request=request, json={"code": 200, "status": "ok"})

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is True
    assert result["credential_mode"] == "dedicated_posture"


@pytest.mark.asyncio
async def test_pfsense_read_timeout_reports_response_stage(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_API_KEY", "key")
    monkeypatch.delenv("PFSENSE_POSTURE_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow pfSense response", request=request)

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is False
    assert result["error_kind"] == "read_timeout"
    assert result["failure_stage"] == "response"
    assert result["path"] == "/api/v2/system/version"
    assert result["attempts"] == 1
    assert "accepted the connection" in result["error"]
    assert "within 4s" in result["error"]


def test_pfsense_liveness_probe_budget_and_backoff_are_bounded() -> None:
    assert platform_health._PFSENSE_CONNECT_TIMEOUT_SEC == 2.0
    assert platform_health._PFSENSE_READ_TIMEOUT_SEC == 4.0
    assert platform_health._PFSENSE_MAX_ATTEMPTS == 1
    assert platform_health._PFSENSE_CACHE_POLICY.success_ttl == 60.0
    assert platform_health._PFSENSE_CACHE_POLICY.failure_ttl == 120.0
    assert platform_health._PFSENSE_CACHE_POLICY.stale_ttl == 600.0


@pytest.mark.asyncio
async def test_pfsense_cache_serves_last_good_result_after_transient_failure(
    monkeypatch,
) -> None:
    await platform_health.reset_pfsense_api_cache()
    results = iter(
        [
            {"reachable": True, "http_status": 200},
            {"reachable": False, "error": "temporary timeout"},
        ],
    )

    async def check():
        return next(results)

    monkeypatch.setattr(platform_health, "check_pfsense_api", check)
    first = await platform_health.get_pfsense_api_snapshot()
    _expire_current_value(platform_health._PFSENSE_CACHE_KEY)
    stale = await platform_health.get_pfsense_api_snapshot()

    assert first["reachable"] is True
    assert stale["reachable"] is True
    assert stale["stale"] is True
    assert stale["refresh_error"] == "temporary timeout"
    await platform_health.reset_pfsense_api_cache()
