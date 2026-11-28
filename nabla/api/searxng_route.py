"""HTTP route for SearXNG web search (TrueNAS LAN App)."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.searxng_search import web_search
from nabla.config_settings import get_settings

router = APIRouter(prefix="/v1/searxng")


class SearxngSearchBody(BaseModel):
    """Request body for POST ``/v1/searxng/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    max_results: int = Field(
        default_factory=lambda: get_settings().web_search_max_results,
        ge=1,
        le=5,
        description="Number of results (hard-capped to 5).",
    )


@router.post("/search", operation_id="searxng")
def post_searxng_search(body: SearxngSearchBody) -> dict[str, Any]:
    """Search the web through the homelab SearXNG (requires ``SEARXNG_URL``; TrueNAS only)."""
    try:
        return web_search(body.query, max_results=body.max_results)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
