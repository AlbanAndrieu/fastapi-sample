"""HTTP routes for Google Custom Search (Programmable Search JSON API)."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nabla.integrations.google_programmable_search import google_programmable_search

router = APIRouter(prefix="/v1/google")


class GoogleSearchBody(BaseModel):
    """Request body for POST ``/v1/google/search``."""

    query: str = Field(..., min_length=1, description="Search query.")
    num: int = Field(
        default=10,
        ge=1,
        le=10,
        description="Number of results (Custom Search allows up to 10 per request).",
    )


@router.post("/search", operation_id="google")
def post_google_search(body: GoogleSearchBody) -> dict[str, Any] | JSONResponse:
    """Perform a Google Custom Search (requires ``GOOGLE_SEARCH_API_KEY`` and cx)."""
    try:
        return google_programmable_search(body.query, num=body.num)
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
