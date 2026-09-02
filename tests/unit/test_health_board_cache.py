"""Single-flight stale-while-revalidate health-board behavior."""

import asyncio

import pytest
from starlette.requests import Request

from nabla.api import health_board


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/health-board", "headers": []})


@pytest.mark.asyncio
async def test_first_health_board_request_returns_pending_then_cached(monkeypatch) -> None:
    await health_board.reset_health_board_cache()
    release = asyncio.Event()
    calls = 0

    async def build(_request):
        nonlocal calls
        calls += 1
        await release.wait()
        return {
            "schema_version": 1,
            "generated_at": "2026-09-02T00:00:00Z",
            "healthz": {"status": "healthy"},
            "homelab": {},
            "sickz": {},
        }

    monkeypatch.setattr(health_board, "build_health_board_snapshot", build)
    pending = await health_board.get_health_board_snapshot(_request())
    duplicate = await health_board.get_health_board_snapshot(_request())
    assert pending["state"] == "pending"
    assert duplicate["state"] == "pending"

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    cached = await health_board.get_health_board_snapshot(_request())

    assert calls == 1
    assert cached["state"] == "fresh"
    assert cached["healthz"]["status"] == "healthy"
    await health_board.reset_health_board_cache()
