"""HTTP routes for Appwrite integration."""

from typing import Any

from fastapi import APIRouter, HTTPException

from nabla.integrations.appwrite_client import appwrite_health

router = APIRouter(prefix="/v1/appwrite")


@router.get("/health", operation_id="appwrite_health")
def get_appwrite_health() -> dict[str, Any]:
    """Return Appwrite backend health (requires Appwrite SDK + credentials)."""
    try:
        return appwrite_health()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
