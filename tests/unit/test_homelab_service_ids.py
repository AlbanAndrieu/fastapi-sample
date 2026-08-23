"""Stable-ID regression tests for homelab catalog and health snapshots."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


@pytest.mark.asyncio
async def test_public_snapshot_uses_catalog_service_id() -> None:
    service = HomelabService(
        name="Langfuse",
        tunnelUrl="https://langfuse.albandrieu.com",
        external=True,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshot = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert service.service_id == "langfuse"
    assert snapshot["id"] == "langfuse"
    assert snapshot["name"] == "Langfuse"
    assert snapshot["url"] == "https://langfuse.albandrieu.com/"


@pytest.mark.asyncio
async def test_internal_snapshot_uses_same_service_id(monkeypatch) -> None:
    service = HomelabService(
        name="Langfuse",
        tunnelUrl="https://langfuse.albandrieu.com",
        internalHost="172.17.0.24",
        internalPort=3000,
        external=True,
    )
    writer = Mock()
    writer.wait_closed = AsyncMock()
    monkeypatch.setattr(
        asyncio,
        "open_connection",
        AsyncMock(return_value=(Mock(), writer)),
    )

    snapshot = await homelab_health._probe_internal_service(
        asyncio.Semaphore(1),
        service,
    )

    assert snapshot["id"] == service.service_id == "langfuse"
    assert snapshot["host"] == "172.17.0.24"
    assert snapshot["port"] == 3000
