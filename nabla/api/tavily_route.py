"""HTTP routes for Tavily web search."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.tavily_search import tavily_search

router = APIRouter(prefix="/v1/tavily")


class TavilySearchBody(BaseModel):
    """Request body for POST ``/v1/tavily/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = Field(
        default="advanced",
        description="Tavily search depth.",
    )


@router.post("/search")
def post_tavily_search(body: TavilySearchBody) -> dict[str, Any]:
    """Perform a Tavily search (requires ``TAVILY_API_KEY``)."""
    try:
        return tavily_search(body.query, search_depth=body.search_depth)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
