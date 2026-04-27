"""HTTP routes for Tavily web search."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.tavily_search import web_search
from nabla.config_settings import get_settings

router = APIRouter(prefix="/v1/tavily")


class TavilySearchBody(BaseModel):
    """Request body for POST ``/v1/tavily/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    max_results: int = Field(
        default_factory=lambda: get_settings().web_search_max_results,
        ge=1,
        le=5,
        description="Number of results (hard-capped to 5).",
    )
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = Field(
        default="advanced",
        description="Tavily search depth.",
    )


@router.post("/search", operation_id="tavily")
def post_tavily_search(body: TavilySearchBody) -> dict[str, Any]:
    """Perform a Tavily search (requires ``TAVILY_API_KEY``)."""
    try:
        return web_search(body.query, search_depth=body.search_depth, max_results=body.max_results)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
