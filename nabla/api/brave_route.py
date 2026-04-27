"""HTTP routes for Brave Web Search."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.brave_search import web_search
from nabla.config_settings import get_settings

router = APIRouter(prefix="/v1/brave")


class BraveSearchBody(BaseModel):
    """Request body for POST ``/v1/brave/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    count: int = Field(
        default_factory=lambda: get_settings().web_search_max_results,
        ge=1,
        le=5,
        description="Number of results (hard-capped to 5).",
    )


@router.post("/search", operation_id="brave")
def post_brave_search(body: BraveSearchBody) -> dict[str, Any]:
    """Perform a Brave Web Search (requires ``BRAVE_API_KEY``)."""
    try:
        return web_search(body.query, count=body.count)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
