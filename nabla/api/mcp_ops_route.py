"""Operational endpoints for configured MCP clients (list servers, tools, dry-run call)."""

from __future__ import annotations

import json
from secrets import compare_digest
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from nabla.config_settings import get_settings
from nabla.mcp.client import list_mcp_tools_for_server, mcp_call_tool

router = APIRouter(prefix="/v1/mcp/ops")


def _require_ops_key(x_mcp_ops_key: str | None) -> None:
    settings = get_settings()
    expected = settings.mcp_ops_key
    if expected is None:
        if getattr(settings, "mcp_ops_require_key", False):
            raise HTTPException(status_code=503, detail="MCP operations access key is not configured")
        return
    if not x_mcp_ops_key or not compare_digest(
        x_mcp_ops_key.strip(),
        expected.get_secret_value(),
    ):
        raise HTTPException(status_code=403, detail="Missing or invalid X-MCP-Ops-Key")


@router.get("/servers")
async def list_mcp_servers(
    x_mcp_ops_key: Annotated[str | None, Header(alias="X-MCP-Ops-Key")] = None,
) -> dict[str, Any]:
    """Return configured MCP client definitions (secrets in ``env`` are not redacted — protect this route)."""
    _require_ops_key(x_mcp_ops_key)
    servers = []
    for c in get_settings().mcp_clients:
        servers.append(
            {
                "name": c.name,
                "transport": c.transport,
                "command": c.command,
                "args": list(c.args),
                "enabled": c.enabled,
                "cwd": c.cwd,
                "env_keys": sorted(c.env.keys()) if c.env else [],
            },
        )
    return {"servers": servers}


@router.get("/servers/{server_name}/tools")
async def list_tools_for_server(
    server_name: str,
    x_mcp_ops_key: Annotated[str | None, Header(alias="X-MCP-Ops-Key")] = None,
) -> dict[str, Any]:
    """List tools from a configured MCP server (spawns stdio server)."""
    _require_ops_key(x_mcp_ops_key)
    try:
        tools = await list_mcp_tools_for_server(server_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"server": server_name, "tools": tools}


class McpToolCallBody(BaseModel):
    """Body for dry-run MCP ``tools/call``."""

    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.post("/servers/{server_name}/call")
async def call_tool_on_server(
    server_name: str,
    body: McpToolCallBody,
    x_mcp_ops_key: Annotated[str | None, Header(alias="X-MCP-Ops-Key")] = None,
) -> dict[str, Any]:
    """Invoke a tool on a configured MCP server (diagnostics; can be expensive)."""
    _require_ops_key(x_mcp_ops_key)
    try:
        return await mcp_call_tool(server_name, body.tool_name, body.arguments)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=json.dumps({"error": str(exc)})) from exc
