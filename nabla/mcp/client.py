"""Spawn stdio MCP server subprocesses and invoke tools (per-call sessions)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from nabla.config_settings import McpServerConfig, get_settings

logger = logging.getLogger(__name__)


def _find_server_config(server_name: str) -> McpServerConfig:
    settings = get_settings()
    for cfg in settings.mcp_clients:
        if cfg.name == server_name and cfg.enabled:
            return cfg
    msg = f"No enabled MCP server named {server_name!r} in settings.mcp_clients"
    raise KeyError(msg)


def _call_tool_result_to_payload(result: Any) -> dict[str, Any]:
    """Serialize ``mcp.types.CallToolResult`` to JSON-friendly dict."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", exclude_none=True)
    return {"content": str(result)}


async def list_mcp_tools_for_server(server_name: str) -> list[dict[str, Any]]:
    """Return ``tools/list`` entries for the given configured MCP server."""
    cfg = _find_server_config(server_name)
    from mcp import ClientSession  # noqa: PLC0415 — optional heavy import
    from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415

    params = StdioServerParameters(
        command=cfg.command,
        args=list(cfg.args),
        env=cfg.env or None,
        cwd=cfg.cwd,
    )
    timeout = timedelta(seconds=cfg.startup_timeout_seconds)
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timeout,
        ) as session:
            await session.initialize()
            out = await session.list_tools()
            return [t.model_dump(mode="json", exclude_none=True) for t in out.tools]


async def mcp_call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ``tools/call`` on the configured MCP server and return a JSON-serializable result."""
    cfg = _find_server_config(server_name)
    from mcp import ClientSession  # noqa: PLC0415
    from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415

    params = StdioServerParameters(
        command=cfg.command,
        args=list(cfg.args),
        env=cfg.env or None,
        cwd=cfg.cwd,
    )
    timeout = timedelta(seconds=cfg.tool_call_timeout_seconds)
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timeout,
        ) as session:
            await session.initialize()
            result = await session.call_tool(
                tool_name,
                arguments=arguments or {},
                read_timeout_seconds=timeout,
            )
            return _call_tool_result_to_payload(result)
