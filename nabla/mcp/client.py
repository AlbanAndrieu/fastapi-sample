"""Outbound MCP clients over stdio or Streamable HTTP."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from typing import Any, AsyncIterator

from nabla.config_settings import McpServerConfig, get_settings

logger = logging.getLogger(__name__)


class McpClientManager:
    """Own long-lived outbound MCP sessions for the FastAPI lifespan."""

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}

    @property
    def started(self) -> bool:
        return self._stack is not None

    async def start(self) -> None:
        """Connect enabled MCP clients without making app startup depend on them."""
        if self._stack is not None:
            return

        stack = AsyncExitStack()
        await stack.__aenter__()
        self._stack = stack

        for cfg in get_settings().mcp_clients:
            if not cfg.enabled:
                continue
            try:
                self._sessions[cfg.name] = await self._connect(cfg, stack)
                logger.info("Connected outbound MCP %s via %s", cfg.name, cfg.transport)
            except Exception:
                logger.exception("Unable to connect outbound MCP %s via %s", cfg.name, cfg.transport)

    async def close(self) -> None:
        """Close persistent MCP sessions and their transports."""
        stack = self._stack
        self._stack = None
        self._sessions.clear()
        if stack is not None:
            await stack.aclose()

    def session(self, server_name: str) -> Any | None:
        return self._sessions.get(server_name)

    async def _connect(self, cfg: McpServerConfig, stack: AsyncExitStack) -> Any:
        from mcp import ClientSession  # noqa: PLC0415 -- optional heavy import

        read, write = await _enter_transport(cfg, stack)
        timeout = timedelta(seconds=cfg.tool_call_timeout_seconds)
        session = await stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=timeout),
        )
        await session.initialize()
        return session


_MANAGER = McpClientManager()


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


async def _enter_transport(cfg: McpServerConfig, stack: AsyncExitStack) -> tuple[Any, Any]:
    if cfg.transport == "stdio":
        if not cfg.command:
            raise ValueError(f"MCP server {cfg.name!r}: command is required for stdio")
        from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415

        params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args),
            env=cfg.env or None,
            cwd=cfg.cwd,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        return read, write

    if cfg.transport == "streamable-http":
        if not cfg.url:
            raise ValueError(f"MCP server {cfg.name!r}: url is required for Streamable HTTP")
        import httpx  # noqa: PLC0415
        from mcp.client.streamable_http import streamable_http_client  # noqa: PLC0415

        timeout = httpx.Timeout(
            cfg.startup_timeout_seconds,
            read=cfg.tool_call_timeout_seconds,
        )
        http_client = await stack.enter_async_context(
            httpx.AsyncClient(
                headers=cfg.headers or None,
                timeout=timeout,
                follow_redirects=True,
            ),
        )
        read, write, _get_session_id = await stack.enter_async_context(
            streamable_http_client(cfg.url, http_client=http_client),
        )
        return read, write

    raise ValueError(f"Unsupported MCP transport: {cfg.transport!r}")


@asynccontextmanager
async def _one_shot_session(cfg: McpServerConfig) -> AsyncIterator[Any]:
    """Fallback when an MCP was unavailable during application startup."""
    from mcp import ClientSession  # noqa: PLC0415

    async with AsyncExitStack() as stack:
        read, write = await _enter_transport(cfg, stack)
        timeout = timedelta(seconds=cfg.tool_call_timeout_seconds)
        session = await stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=timeout),
        )
        await session.initialize()
        yield session


async def initialize_mcp_clients() -> None:
    """Initialize persistent outbound MCP sessions for the application lifespan."""
    await _MANAGER.start()


async def close_mcp_clients() -> None:
    """Close all persistent outbound MCP sessions."""
    await _MANAGER.close()


async def list_mcp_tools_for_server(server_name: str) -> list[dict[str, Any]]:
    """Return ``tools/list`` entries for the given configured MCP server."""
    cfg = _find_server_config(server_name)
    session = _MANAGER.session(server_name)
    if session is not None:
        out = await session.list_tools()
        return [tool.model_dump(mode="json", exclude_none=True) for tool in out.tools]

    async with _one_shot_session(cfg) as fallback_session:
        out = await fallback_session.list_tools()
        return [tool.model_dump(mode="json", exclude_none=True) for tool in out.tools]


async def mcp_call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ``tools/call`` and return a JSON-serializable result."""
    cfg = _find_server_config(server_name)
    timeout = timedelta(seconds=cfg.tool_call_timeout_seconds)
    session = _MANAGER.session(server_name)
    if session is not None:
        result = await session.call_tool(
            tool_name,
            arguments=arguments or {},
            read_timeout_seconds=timeout,
        )
        return _call_tool_result_to_payload(result)

    async with _one_shot_session(cfg) as fallback_session:
        result = await fallback_session.call_tool(
            tool_name,
            arguments=arguments or {},
            read_timeout_seconds=timeout,
        )
        return _call_tool_result_to_payload(result)
