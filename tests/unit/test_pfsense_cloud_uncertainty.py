"""Regression tests for pfSense cloud-vantage uncertainty semantics."""

import httpx
import pytest

from nabla.api import component_health, platform_health


class _ReadTimeoutClient(httpx.AsyncClient):
    def __init__(self, *args, **kwargs) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow pfSense response", request=request)

        kwargs["transport"] = httpx.MockTransport(handler)
        super().__init__(*args, **kwargs)


def _configure_pfsense(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_POSTURE_API_KEY", "posture-key")


@pytest.mark.asyncio
async def test_fastapi_cloud_pfsense_read_timeout_is_unconfirmed_warning(monkeypatch) -> None:
    _configure_pfsense(monkeypatch)
    monkeypatch.setenv("FASTAPI_CLOUD_APP_ID", "app")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", _ReadTimeoutClient)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is None
    assert result["status_confirmed"] is False
    assert result["state"] == "unknown"
    assert result["degraded"] is False
    assert result["error_kind"] == "read_timeout"
    assert result["failure_stage"] == "response"
    assert result["vantage_point"] == "fastapi_cloud"
    assert result["warning"].startswith(
        "⚠️ pfSense status could not be confirmed from FastAPI Cloud",
    )


@pytest.mark.asyncio
async def test_homelab_pfsense_read_timeout_remains_failure(monkeypatch) -> None:
    _configure_pfsense(monkeypatch)
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    monkeypatch.delenv("FASTAPI_CLOUD_APP_ID", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", _ReadTimeoutClient)

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is False
    assert result["error_kind"] == "read_timeout"
    assert result["failure_stage"] == "response"
    assert "status_confirmed" not in result


def test_unconfirmed_pfsense_cloud_probe_does_not_degrade_platform() -> None:
    components = {
        "postgres": {"reachable": True},
        "redis": {"reachable": True},
        "supabase": {"reachable": True},
        "truenas": {"reachable": True, "state": "ok", "tls_trusted": True},
        "cloudflare": {"reachable": True, "status_confirmed": True},
        "pfsense": {
            "reachable": None,
            "state": "unknown",
            "status_confirmed": False,
            "degraded": False,
        },
    }

    assert component_health.component_status(components) == "healthy"
