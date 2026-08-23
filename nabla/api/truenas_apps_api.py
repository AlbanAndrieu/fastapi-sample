"""FastAPI routes for optional TrueNAS application inventory."""

from typing import Any

from fastapi import APIRouter, HTTPException

from nabla.integrations.truenas_apps import get_truenas_apps_json

router = APIRouter()


@router.get("/internal/truenas-apps", tags=["internal"])
def truenas_apps_endpoint() -> dict[str, Any]:
    """Expose the configured TrueNAS application inventory."""
    try:
        return get_truenas_apps_json()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
