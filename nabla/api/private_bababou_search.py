"""Owner-only, corpus-filtered Bababou search over the private OpenRAG MCP.

This endpoint never indexes documents and never offers arbitrary MCP tools.
The regular /run agent must not gain a private OpenRAG tool implicitly.
"""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nabla.config_settings import get_settings
from nabla.mcp.client import mcp_call_tool

router = APIRouter(prefix="/private/ops/ai", tags=["owner-private-rag"])
_FILTER = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")
_PRIVATE_MCP_URL = "http://openrag-frontend:3000/mcp"
_PRIVATE_KEYS = frozenset(("source_path", "file_path", "absolute_path", "local_path", "filesystem_path"))


class BababouSearch(BaseModel):
    """A bounded search request; caller cannot select the corpus."""

    query: str = Field(min_length=3, max_length=300)
    limit: int = Field(default=5, ge=1, le=5)


def search_configuration_ready() -> bool:
    """Fail closed until a single private MCP client and filter are configured."""
    filter_id = os.environ.get("OPENRAG_BABABOU_FILTER_ID", "")
    if not _FILTER.fullmatch(filter_id):
        return False
    clients = [c for c in get_settings().mcp_clients if c.name == "openrag" and c.enabled]
    if len(clients) != 1:
        return False
    client = clients[0]
    if client.transport != "streamable-http" or client.url != _PRIVATE_MCP_URL:
        return False
    # API key is held in sample/.env.secrets, never in the Git/Compose config.
    return any(name.lower() == "x-api-key" and bool(value.strip())
               for name, value in client.headers.items())


def _redact_paths(item: Any, depth: int = 0) -> Any:
    """Bound OpenRAG response, removing private filesystem metadata."""
    if depth > 9:
        return None
    if isinstance(item, dict):
        return {str(k)[:80]: _redact_paths(v, depth + 1)
                for k, v in list(item.items())[:100]
                if str(k).lower() not in _PRIVATE_KEYS}
    if isinstance(item, list):
        return [_redact_paths(v, depth + 1) for v in item[:25]]
    if isinstance(item, str):
        return re.sub(r"/mnt/(?:cpool/)?bababou/[^\s\"'<>]+", "[private-file]", item[:16000])
    if isinstance(item, (int, float, bool)) or item is None:
        return item
    return None


@router.post("/bababou/search", response_model=None)
async def search_bababou(body: BababouSearch) -> JSONResponse:
    """Search only the authorized Bababou knowledge filter; no chat/ingest/delete.

    /private/ops routes are guarded by owner JWT and trusted-source policy in
    operations_access_middleware, before this handler runs.
    """
    if not search_configuration_ready():
        raise HTTPException(status_code=503, detail="Private RAG not configured")
    filter_id = os.environ["OPENRAG_BABABOU_FILTER_ID"]
    try:
        result = await mcp_call_tool(
            "openrag", "openrag_search",
            {"query": body.query, "limit": body.limit, "filter_id": filter_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Private RAG unavailable") from None
    return JSONResponse(
        content={"status": "retrieved", "result": _redact_paths(result)},
        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"},
    )
