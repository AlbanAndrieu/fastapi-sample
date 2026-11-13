"""Stable-ID regression tests for Backstage v2 routes and health snapshots."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_service_health import build_reconciled_service_health
from tests.unit.catalog_v2_fixture import service as v2_service


def test_route_without_hostname_keeps_entity_name_navigation_identity() -> None:
    service = v2_service("prometheus-albandrieu", backend=("172.17.0.24", 9090))

    rows = build_reconciled_service_health(
        [service],
        public_results=[],
        internal_results=[],
        runtime=None,
        tunnels=[],
    )

    assert rows[0]["id"] == "prometheus-albandrieu"
    assert rows[0]["entity_ref"] == "component:default/prometheus-albandrieu"
    assert rows[0]["url"] == "https://prometheus-albandrieu.albandrieu.com/"
    assert rows[0]["url_derived"] is True


@pytest.mark.asyncio
async def test_public_snapshot_uses_catalog_service_id() -> None:
    service = v2_service("langfuse-web", "https://langfuse.albandrieu.com", title="Langfuse", public=True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshot = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert service.service_id == "langfuse-web"
    assert snapshot["id"] == "langfuse-web"
    assert snapshot["name"] == "Langfuse"
    assert snapshot["url"] == "https://langfuse.albandrieu.com/"


@pytest.mark.asyncio
async def test_internal_snapshot_uses_same_service_id(monkeypatch) -> None:
    service = v2_service(
        "langfuse-web",
        "https://langfuse.albandrieu.com",
        title="Langfuse",
        public=True,
        backend=("172.17.0.24", 3000),
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

    assert snapshot["id"] == service.service_id == "langfuse-web"
    assert snapshot["host"] == "172.17.0.24"
    assert snapshot["port"] == 3000
