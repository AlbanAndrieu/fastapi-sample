"""Tests for the public homelab catalog and health API."""

import asyncio
import warnings
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api import health_board, homelab_catalog, homelab_health
from nabla.api.homelab_models import HomelabCatalog, HomelabService
from nabla.config import CORS_ORIGINS
from nabla.routes import register_routes


@pytest.mark.asyncio
async def test_health_snapshot_only_probes_approved_public_services(monkeypatch) -> None:
    services = [
        HomelabService(
            name="Langfuse",
            tunnelUrl="https://langfuse.albandrieu.com",
            external=True,
        ),
        HomelabService(
            name="Disabled",
            tunnelUrl="https://disabled.albandrieu.com",
            external=True,
            endpointEnabled=False,
        ),
        HomelabService(
            name="Private",
            tunnelUrl="https://hello.int.albandrieu.com",
            external=False,
        ),
    ]
    probe = AsyncMock(
        return_value={
            "id": services[0].service_id,
            "name": "Langfuse",
            "url": "https://langfuse.albandrieu.com/",
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 1,
        },
    )
    truenas_probe = AsyncMock(
        return_value={
            "state": "ok",
            "public": {"state": "ok"},
            "internal": None,
            "internal_probe_enabled": False,
        },
    )

    monkeypatch.delenv("HOMELAB_INTERNAL_PROBES_ENABLED", raising=False)
    monkeypatch.setattr(
        homelab_health,
        "fetch_homelab_services",
        AsyncMock(return_value=services),
    )
    monkeypatch.setattr(homelab_health, "_probe_public_service", probe)
    monkeypatch.setattr(homelab_health, "_probe_truenas", truenas_probe)
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)

    payload = await homelab_health.build_homelab_health_payload()

    assert payload["schema_version"] == 3
    assert payload["truenas"]["state"] == "ok"
    assert len(payload["services"]) == 1
    assert payload["services"][0]["url"] == "https://langfuse.albandrieu.com/"
    assert payload["internal_probes_enabled"] is False
    assert payload["internal_services"] == []
    assert probe.await_count == 1
    assert truenas_probe.await_count == 1


@pytest.mark.asyncio
async def test_internal_probes_cover_private_and_external_services(monkeypatch) -> None:
    services = [
        HomelabService(
            name="Private service",
            internalHost="192.168.1.20",
            internalPort=8080,
            external=False,
        ),
        HomelabService(
            name="Exposed service",
            internalHost="192.168.1.21",
            internalPort=3000,
            tunnelUrl="https://service.albandrieu.com",
            external=True,
        ),
        HomelabService(name="No internal endpoint", external=False),
    ]
    internal_probe = AsyncMock(
        side_effect=[
            {
                "id": services[0].service_id,
                "name": "Private service",
                "host": "192.168.1.20",
                "port": 8080,
                "reachable": True,
                "state": "ok",
                "latency_ms": 1,
            },
            {
                "id": services[1].service_id,
                "name": "Exposed service",
                "host": "192.168.1.21",
                "port": 3000,
                "reachable": True,
                "state": "ok",
                "latency_ms": 1,
            },
        ],
    )

    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", "true")
    monkeypatch.setattr(
        homelab_health,
        "fetch_homelab_services",
        AsyncMock(return_value=services),
    )
    monkeypatch.setattr(homelab_health, "_probe_internal_service", internal_probe)
    monkeypatch.setattr(
        homelab_health,
        "_probe_public_service",
        AsyncMock(
            return_value={
                "id": services[1].service_id,
                "name": "Exposed service",
                "url": "https://service.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
                "latency_ms": 1,
            },
        ),
    )
    monkeypatch.setattr(
        homelab_health,
        "_probe_truenas",
        AsyncMock(
            return_value={
                "state": "ok",
                "public": {"state": "ok"},
                "internal": {"state": "ok"},
                "internal_probe_enabled": True,
            },
        ),
    )
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)

    payload = await homelab_health.build_homelab_health_payload()

    assert payload["internal_probes_enabled"] is True
    assert [row["name"] for row in payload["internal_services"]] == [
        "Private service",
        "Exposed service",
    ]
    assert internal_probe.await_count == 2


@pytest.mark.asyncio
async def test_global_health_rows_always_include_truenas(monkeypatch) -> None:
    monkeypatch.setattr(
        homelab_catalog,
        "fetch_homelab_services",
        AsyncMock(return_value=[]),
    )

    rows = await homelab_catalog.homelab_healthz_probe_rows()

    assert rows[0][:3] == (
        "albandrieu_truenas",
        "https://truenas.albandrieu.com:7000/",
        "TrueNAS HTTPS",
    )


def test_public_homelab_routes(monkeypatch) -> None:
    health_payload = {
        "schema_version": 3,
        "checked_at": "2026-08-23T00:00:00Z",
        "truenas": {
            "state": "fail",
            "public": {"state": "fail"},
            "internal": None,
            "internal_probe_enabled": False,
        },
        "services": [],
        "internal_probes_enabled": False,
        "internal_services": [],
    }
    catalog = HomelabCatalog(
        version=2,
        services=[
            HomelabService(
                name="Langfuse",
                tunnelUrl="https://langfuse.albandrieu.com",
                external=True,
            ),
        ],
    )
    health_snapshot = {
        "schema_version": 6,
        "checked_at": health_payload["checked_at"],
        "truenas": health_payload["truenas"],
        "services": [
            {
                "id": "langfuse",
                "name": "Langfuse",
                "url": "https://langfuse.albandrieu.com/",
                "url_derived": False,
                "state": "unknown",
            },
        ],
    }
    monkeypatch.setattr(
        health_board,
        "build_homelab_snapshot",
        AsyncMock(return_value=health_snapshot),
    )
    monkeypatch.setattr(
        homelab_health,
        "build_homelab_health_payload",
        AsyncMock(return_value=health_payload),
    )
    monkeypatch.setattr(
        homelab_catalog,
        "fetch_homelab_catalog",
        AsyncMock(return_value=catalog),
    )

    app = FastAPI()
    register_routes(app)
    client = TestClient(app)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        health_response = client.get("/api/homelab/health")
        probes_response = client.get("/api/homelab/probes")
        catalog_response = client.get("/api/homelab-services")

    assert health_response.status_code == 200
    health_body = health_response.json()
    assert health_body["schema_version"] == 6
    assert health_body["checked_at"] == health_payload["checked_at"]
    assert health_body["truenas"] == health_payload["truenas"]
    assert len(health_body["services"]) == 1
    service_health = health_body["services"][0]
    assert service_health["id"] == "langfuse"
    assert service_health["name"] == "Langfuse"
    assert service_health["url"] == "https://langfuse.albandrieu.com/"
    assert service_health["url_derived"] is False
    assert service_health["state"] == "unknown"
    assert probes_response.status_code == 200
    assert probes_response.json()["schema_version"] == 3
    assert catalog_response.status_code == 200
    assert catalog_response.json()["version"] == 2
    assert catalog_response.json()["services"][0]["external"] is True
    assert not any("ORJSONResponse is deprecated" in str(item.message) for item in caught)


def test_cors_origins_include_public_site_and_fastapi_cloud() -> None:
    assert "https://www.albanandrieu.com" in CORS_ORIGINS
    assert "https://fastapi-sample.fastapicloud.dev" in CORS_ORIGINS
    assert all(not origin.endswith("/") for origin in CORS_ORIGINS)


@pytest.mark.asyncio
async def test_truenas_transport_diagnostics_timeout_keeps_api_health(monkeypatch) -> None:
    async def api_ok():
        return {
            "reachable": True,
            "version": "TrueNAS-26.0.0-BETA.2",
            "apps": [{"id": "sample"}],
        }

    async def http_ok(*_args, **_kwargs):
        return {
            "name": "TrueNAS HTTPS",
            "url": "https://truenas.albandrieu.com:7000/",
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 1,
        }

    async def slow_diagnostics(**_kwargs):
        await asyncio.sleep(1)
        return {"stages": []}

    monkeypatch.setattr(homelab_health, "_observe_truenas_api", api_ok)
    monkeypatch.setattr(homelab_health, "_probe_http_endpoint", http_ok)
    monkeypatch.setattr(
        homelab_health,
        "collect_truenas_network_diagnostics",
        slow_diagnostics,
    )
    monkeypatch.setattr(homelab_health, "_TRUENAS_DIAGNOSTICS_BUDGET_SEC", 0.01)
    monkeypatch.setattr(
        homelab_health,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(
        homelab_health,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(homelab_health, "truenas_http_verify_ssl", lambda: True)
    monkeypatch.setattr(homelab_health, "homelab_runtime_detected", lambda: True)

    result = await homelab_health._probe_truenas(
        asyncio.Semaphore(2),
        internal_enabled=False,
    )

    assert result["state"] == "ok"
    assert result["public"]["name"] == "TrueNAS HTTPS"
    assert result["api"]["reachable"] is True
    assert result["diagnostics"]["timed_out"] is True
    assert result["diagnostics"]["error_kind"] == "deadline"
    assert result["diagnostics"]["stages"][-2]["id"] == "authentication"
    assert result["diagnostics"]["stages"][-2]["state"] == "ok"
    assert result["diagnostics"]["stages"][-1]["id"] == "api"
    assert result["diagnostics"]["stages"][-1]["state"] == "ok"
