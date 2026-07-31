"""MCP client helpers and in-process A2A Starlette app."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from nabla.a2a_app import build_a2a_starlette_application
from nabla.api import mcp_ops_route
from nabla.mcp.client import mcp_call_tool


@pytest.mark.asyncio
async def test_mcp_call_tool_unknown_server(monkeypatch: pytest.MonkeyPatch) -> None:
    def _empty() -> SimpleNamespace:
        return SimpleNamespace(mcp_clients=[])

    monkeypatch.setattr("nabla.mcp.client.get_settings", _empty)

    with pytest.raises(KeyError, match="No enabled MCP server"):
        await mcp_call_tool("missing", "any_tool", {})


@pytest.mark.asyncio
async def test_a2a_agent_card_json() -> None:
    settings = SimpleNamespace(a2a_public_base_url="https://api.example.com")
    app = build_a2a_starlette_application(settings)  # type: ignore[arg-type]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/.well-known/agent-card.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "nabla-deep-agent"
    assert any("a2a" in (iface.get("url") or "") for iface in data.get("supportedInterfaces", []))


@pytest.mark.asyncio
async def test_mcp_ops_requires_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        mcp_ops_key=SecretStr("secret-ops"),
        mcp_clients=[],
    )
    monkeypatch.setattr("nabla.api.mcp_ops_route.get_settings", lambda: fake)
    mini = FastAPI()
    mini.include_router(mcp_ops_route.router)
    async with AsyncClient(transport=ASGITransport(app=mini), base_url="http://test") as client:
        r = await client.get("/v1/mcp/ops/servers")
        r2 = await client.get("/v1/mcp/ops/servers", headers={"X-MCP-Ops-Key": "secret-ops"})
    assert r.status_code == 403
    assert r2.status_code == 200
    assert "servers" in r2.json()
