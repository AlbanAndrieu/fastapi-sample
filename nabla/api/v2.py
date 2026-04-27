from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

router = APIRouter(prefix="/v2")


@router.get("/version", operation_id="ver")
def api_version(request: Request) -> dict[str, str]:
    """Application version (same payload as legacy ``/version`` / ``/v/version``)."""
    return {"version": request.app.version}


@router.get("/ping")
def ping():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v2!"})
