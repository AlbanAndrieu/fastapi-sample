"""Freebox checks must remain read-only, LAN-scoped and unambiguous."""
import httpx
import pytest

from nabla.api import freebox_health as fh


@pytest.mark.asyncio
async def test_freebox_api_version_ok_only_from_lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "freebox")
    monkeypatch.setenv("FREEBOX_BASE_URL", "http://192.168.1.254")
    monkeypatch.setattr(fh, "known_paas_runtime_detected", lambda: False)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        return httpx.Response(200, json={"api_version": "11.0", "api_domain": "hidden"})

    result = await fh.check_freebox_api(transport=httpx.MockTransport(handler))
    assert seen == [("GET", "http://192.168.1.254/api_version")]
    assert result["state"] == "ok"
    assert result["status_confirmed"] is True
    assert result["api_version"] == "11.0"
    assert "api_domain" not in result


@pytest.mark.asyncio
async def test_freebox_never_queried_from_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "freebox")
    monkeypatch.setattr(fh, "known_paas_runtime_detected", lambda: True)

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("Cloud must never probe a private Freebox address")

    result = await fh.check_freebox_api(transport=httpx.MockTransport(handler))
    assert result["skipped"] is True
    assert result["reachable"] is None
    assert result["vantage_point"] == "fastapi_cloud"


@pytest.mark.asyncio
async def test_freebox_rejects_unapproved_origins_before_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "freebox")
    monkeypatch.setenv("FREEBOX_BASE_URL", "http://example.org")
    monkeypatch.setattr(fh, "known_paas_runtime_detected", lambda: False)

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unapproved URL must never be requested")

    result = await fh.check_freebox_api(transport=httpx.MockTransport(handler))
    assert result["skipped"] is True
    assert result["status_confirmed"] is False


@pytest.mark.asyncio
async def test_freebox_timeout_does_not_assert_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "freebox")
    monkeypatch.setattr(fh, "known_paas_runtime_detected", lambda: False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("not reachable")

    result = await fh.check_freebox_api(transport=httpx.MockTransport(handler))
    assert result["state"] == "unknown"
    assert result["reachable"] is None
    assert result["status_confirmed"] is False


@pytest.mark.asyncio
async def test_pfSense_retirement_flag_preserves_legacy_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.api.edge_provider import pfsense_retired
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "freebox")
    assert pfsense_retired()
    monkeypatch.setenv("NETWORK_EDGE_PROVIDER", "pfsense")
    assert not pfsense_retired()
