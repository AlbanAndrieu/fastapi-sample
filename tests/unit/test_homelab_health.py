"""Tests for the public homelab catalog and health API."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api import homelab_catalog, homelab_health
from nabla.api.homelab_models import HomelabCatalog, HomelabService
from nabla.config import CORS_ORIGINS
from nabla.routes import register_routes


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "ok"),
        (301, "ok"),
        (401, "warn"),
        (403, "warn"),
        (407, "warn"),
        (429, "warn"),
        (404, "fail"),
        (500, "fail"),
        (530, "fail"),
        (0, "fail"),
    ],
)
def test_classify_public_http_status(status: int, expected: str) -> None:
    assert homelab_health.classify_public_http_status(status) == expected


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
            "name": "Langfuse",
            "url": "https://langfuse.albandrieu.com/",
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 1,
        }
    )

    monkeypatch.setattr(
        homelab_health,
        "fetch_homelab_services",
        AsyncMock(return_value=services),
    )
    monkeypatch.setattr(homelab_health, "_probe_public_service", probe)
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)

    payload = await homelab_health.build_homelab_health_payload()

    assert payload["schema_version"] == 1
    assert len(payload["services"]) == 1
    assert payload["services"][0]["url"] == "https://langfuse.albandrieu.com/"
    assert probe.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "state"),
    [(200, "ok"), (403, "warn"), (404, "fail"), (530, "fail")],
)
async def test_probe_preserves_real_http_status(status: int, state: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["reachable"] is True
    assert result["http_status"] == status
    assert result["state"] == state
    assert result["tls_trusted"] is True


@pytest.mark.asyncio
async def test_probe_retries_get_when_head_is_not_supported() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        status = 405 if request.method == "HEAD" else 200
        return httpx.Response(status, request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert methods == ["HEAD", "GET"]
    assert result["http_status"] == 200
    assert result["state"] == "ok"


@pytest.mark.asyncio
async def test_probe_reports_tls_failure_as_red() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("certificate verify failed", request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["reachable"] is False
    assert result["http_status"] == 0
    assert result["state"] == "fail"
    assert result["tls_trusted"] is False


def test_public_homelab_routes(monkeypatch) -> None:
    health_payload = {
        "schema_version": 1,
        "checked_at": "2026-08-23T00:00:00Z",
        "services": [],
    }
    catalog = HomelabCatalog(
        version=2,
        services=[
            HomelabService(
                name="Langfuse",
                tunnelUrl="https://langfuse.albandrieu.com",
                external=True,
            )
        ],
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

    health_response = client.get("/api/homelab/health")
    catalog_response = client.get("/api/homelab-services")

    assert health_response.status_code == 200
    assert health_response.json() == health_payload
    assert catalog_response.status_code == 200
    assert catalog_response.json()["version"] == 2
    assert catalog_response.json()["services"][0]["external"] is True


def test_cors_origins_include_public_site_and_fastapi_cloud() -> None:
    assert "https://www.albanandrieu.com" in CORS_ORIGINS
    assert "https://fastapi-sample.fastapicloud.dev" in CORS_ORIGINS
    assert all(not origin.endswith("/") for origin in CORS_ORIGINS)
