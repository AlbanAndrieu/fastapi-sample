"""HTTP routes for Google Custom Search (Programmable Search JSON API)."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nabla.integrations.google_search import web_search
from nabla.config_settings import get_settings

router = APIRouter(prefix="/v1/google")


class GoogleSearchBody(BaseModel):
    """Request body for POST ``/v1/google/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    num: int = Field(
        default_factory=lambda: get_settings().web_search_max_results,
        ge=1,
        le=5,
        description="Number of results (hard-capped to 5).",
    )


@router.post("/search", operation_id="google")
def post_google_search(body: GoogleSearchBody) -> dict[str, Any]:
    """Perform a Google Custom Search (requires ``GOOGLE_SEARCH_API_KEY`` and cx)."""
    try:
        return web_search(body.query, num=body.num)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
