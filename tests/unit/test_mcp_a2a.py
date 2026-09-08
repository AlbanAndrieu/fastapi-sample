"""MCP client helpers and in-process A2A Starlette app."""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastmcp import Client, FastMCP
from pydantic import SecretStr
from starlette.testclient import TestClient

from nabla.a2a_app import build_a2a_starlette_application
from nabla.api import mcp_ops_route
from nabla.config import MCP_ALLOWED_ROUTES
from nabla.config_settings import McpServerConfig
from nabla.mcp.client import mcp_call_tool
from nabla.mcp.resources import register_fastapi_resources


@pytest.mark.asyncio
async def test_mcp_call_tool_unknown_server(monkeypatch: pytest.MonkeyPatch) -> None:
    def _empty() -> SimpleNamespace:
        return SimpleNamespace(mcp_clients=[])

    monkeypatch.setattr("nabla.mcp.client.get_settings", _empty)

    with pytest.raises(KeyError, match="No enabled MCP server"):
        await mcp_call_tool("missing", "any_tool", {})


def test_mcp_streamable_http_config() -> None:
    cfg = McpServerConfig(
        name="remote",
        transport="streamable-http",
        url="https://mcp.example.test/mcp",
        headers={"Authorization": "Bearer secret"},
    )
    assert cfg.transport == "streamable-http"
    assert cfg.command is None
    assert cfg.url == "https://mcp.example.test/mcp"


def test_mcp_stdio_config_keeps_local_transport() -> None:
    cfg = McpServerConfig(name="local", command="uvx", args=["openrag-mcp"])
    assert cfg.transport == "stdio"
    assert cfg.command == "uvx"
    assert cfg.url is None


def test_a2a_agent_card_json() -> None:
    settings = SimpleNamespace(a2a_public_base_url="https://api.example.com")
    app = build_a2a_starlette_application(settings)  # type: ignore[arg-type]
    client = TestClient(app)
    res = client.get("/.well-known/agent-card.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "nabla-deep-agent"
    assert any("a2a" in (iface.get("url") or "") for iface in data.get("supportedInterfaces", []))


def test_mcp_ops_requires_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        mcp_ops_key=SecretStr("secret-ops"),
        mcp_clients=[],
    )
    monkeypatch.setattr("nabla.api.mcp_ops_route.get_settings", lambda: fake)
    mini = FastAPI()
    mini.include_router(mcp_ops_route.router)
    client = TestClient(mini)
    r = client.get("/v1/mcp/ops/servers")
    assert r.status_code == 403
    r2 = client.get("/v1/mcp/ops/servers", headers={"X-MCP-Ops-Key": "secret-ops"})
    assert r2.status_code == 200
    assert "servers" in r2.json()


@pytest.mark.asyncio
async def test_mcp_operations_resource_is_discoverable() -> None:
    server = FastMCP("test")
    register_fastapi_resources(server)

    async with Client(server) as client:
        resources = await client.list_resources()
        assert any(str(resource.uri) == "resource://fastapi/operations" for resource in resources)
        content = await client.read_resource("resource://fastapi/operations")

    payload = json.loads(content[0].text)
    assert payload["service"] == "fastapi-sample"
    assert payload["mcp_endpoint"] == "/mcp"
    assert any(item["endpoint"] == "/api/homelab/status" for item in payload["operations"])


def test_mcp_operational_tools_do_not_bypass_diagnostics_protection() -> None:
    assert ("GET", "/api/homelab/status") in MCP_ALLOWED_ROUTES
    assert ("GET", "/api/homelab/runtime") in MCP_ALLOWED_ROUTES
    assert ("GET", "/api/runtime/topology") in MCP_ALLOWED_ROUTES
    assert ("GET", "/api/homelab/health") not in MCP_ALLOWED_ROUTES
    assert ("GET", "/api/homelab-topology") not in MCP_ALLOWED_ROUTES
    assert ("GET", "/healthz") not in MCP_ALLOWED_ROUTES
    assert ("GET", "/sickz") not in MCP_ALLOWED_ROUTES
