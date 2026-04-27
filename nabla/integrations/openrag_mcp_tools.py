"""LangChain tools that call an OpenRAG (or compatible) MCP server named ``openrag``."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import tool

from nabla.config_settings import get_settings

logger = logging.getLogger(__name__)

OPENRAG_SERVER_NAME = "openrag"


def _openrag_mcp_configured() -> bool:
    return any(c.name == OPENRAG_SERVER_NAME and c.enabled for c in get_settings().mcp_clients)


def _run_async(coro: Any) -> Any:
    """Run async MCP client code from sync tool handlers (worker thread, no running loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    msg = "OpenRAG MCP tools require running outside an active asyncio loop (e.g. wrap agent invoke in anyio.to_thread.run_sync)."
    raise RuntimeError(msg)


def build_openrag_mcp_tools() -> list[Any]:
    """Return LangChain tools when an ``openrag`` MCP server is present in settings."""
    if not _openrag_mcp_configured():
        return []

    @tool
    def openrag_search(query: str, limit: int = 8) -> str:
        """Semantic search the OpenRAG knowledge base (MCP tool ``openrag_search``)."""
        from nabla.mcp.client import mcp_call_tool  # noqa: PLC0415

        async def _go() -> dict[str, Any]:
            return await mcp_call_tool(
                OPENRAG_SERVER_NAME,
                "openrag_search",
                {"query": query, "limit": limit},
            )

        try:
            payload = _run_async(_go())
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception("openrag_search MCP call failed")
            return f"OpenRAG search failed: {exc!s}"

    @tool
    def openrag_chat(message: str, chat_id: str | None = None) -> str:
        """Chat with OpenRAG RAG-backed assistant (MCP tool ``openrag_chat``)."""
        from nabla.mcp.client import mcp_call_tool  # noqa: PLC0415

        args: dict[str, Any] = {"message": message}
        if chat_id:
            args["chat_id"] = chat_id

        async def _go() -> dict[str, Any]:
            return await mcp_call_tool(OPENRAG_SERVER_NAME, "openrag_chat", args)

        try:
            payload = _run_async(_go())
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception("openrag_chat MCP call failed")
            return f"OpenRAG chat failed: {exc!s}"

    return [openrag_search, openrag_chat]
