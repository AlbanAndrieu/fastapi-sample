"""HTTP routes for Brave Web Search."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.brave_search import brave_web_search

router = APIRouter(prefix="/v1/brave")


class BraveSearchBody(BaseModel):
    """Request body for POST ``/v1/brave/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    count: int = Field(default=10, ge=1, le=20, description="Number of results.")


@router.post("/search")
def post_brave_search(body: BraveSearchBody) -> dict[str, Any]:
    """Perform a Brave Web Search (requires ``BRAVE_API_KEY``)."""
    try:
        return brave_web_search(body.query, count=body.count)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
