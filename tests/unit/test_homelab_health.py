"""Tests for the public homelab catalog and health API."""

import asyncio
from unittest.mock import AsyncMock, Mock

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


def test_internal_probes_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("HOMELAB_INTERNAL_PROBES_ENABLED", raising=False)

    assert homelab_health.internal_probes_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_internal_probes_can_be_explicitly_enabled(monkeypatch, value: str) -> None:
    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", value)

    assert homelab_health.internal_probes_enabled() is True


def test_truenas_internal_target_prefers_explicit_configuration(monkeypatch) -> None:
    services = [
        HomelabService(name="App", internalHost="172.17.0.24", internalPort=80)
    ]
    monkeypatch.setenv("TRUENAS_INTERNAL_HOST", "192.168.1.24")
    monkeypatch.setenv("TRUENAS_INTERNAL_PORT", "8443")

    assert homelab_health._truenas_internal_target(services) == (
        "192.168.1.24",
        8443,
    )


def test_truenas_internal_target_falls_back_to_dot_24(monkeypatch) -> None:
    services = [
        HomelabService(name="Other", internalHost="172.17.0.20", internalPort=80),
        HomelabService(name="App", internalHost="172.17.0.24", internalPort=8080),
    ]
    monkeypatch.delenv("TRUENAS_INTERNAL_HOST", raising=False)
    monkeypatch.delenv("TRUENAS_INTERNAL_PORT", raising=False)

    assert homelab_health._truenas_internal_target(services) == ("172.17.0.24", 443)


@pytest.mark.parametrize(
    ("public_state", "internal_state", "expected"),
    [
        ("ok", None, "ok"),
        ("ok", "ok", "ok"),
        ("ok", "fail", "warn"),
        ("warn", None, "warn"),
        ("fail", "ok", "warn"),
        ("fail", "fail", "fail"),
        ("fail", None, "fail"),
    ],
)
def test_truenas_state_distinguishes_host_and_ingress_failures(
    public_state: str,
    internal_state: str | None,
    expected: str,
) -> None:
    public = {"state": public_state}
    internal = {"state": internal_state} if internal_state is not None else None

    assert homelab_health._truenas_state(public, internal) == expected


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
    truenas_probe = AsyncMock(
        return_value={
            "state": "ok",
            "public": {"state": "ok"},
            "internal": None,
            "internal_probe_enabled": False,
        }
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

    assert payload["schema_version"] == 2
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
                "name": "Private service",
                "host": "192.168.1.20",
                "port": 8080,
                "reachable": True,
                "state": "ok",
                "latency_ms": 1,
            },
            {
                "name": "Exposed service",
                "host": "192.168.1.21",
                "port": 3000,
                "reachable": True,
                "state": "ok",
                "latency_ms": 1,
            },
        ]
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
                "name": "Exposed service",
                "url": "https://service.albandrieu.com/",
                "reachable": True,
                "http_status": 200,
                "state": "ok",
                "tls_trusted": True,
                "latency_ms": 1,
            }
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
            }
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
async def test_internal_tcp_probe_reports_reachability(monkeypatch) -> None:
    writer = Mock()
    writer.wait_closed = AsyncMock()
    open_connection = AsyncMock(return_value=(Mock(), writer))
    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    service = HomelabService(
        name="Internal service",
        internalHost="192.168.1.30",
        internalPort=8443,
        external=False,
    )

    result = await homelab_health._probe_internal_service(
        asyncio.Semaphore(1),
        service,
    )

    open_connection.assert_awaited_once_with("192.168.1.30", 8443)
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once_with()
    assert result["reachable"] is True
    assert result["state"] == "ok"
    assert result["host"] == "192.168.1.30"
    assert result["port"] == 8443


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
        "TrueNAS",
    )


def test_public_homelab_routes(monkeypatch) -> None:
    health_payload = {
        "schema_version": 2,
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
