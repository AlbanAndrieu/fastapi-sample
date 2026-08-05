from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from nabla.version import API_VERSION, RELEASE_VERSION

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

router = APIRouter(prefix="/v2")


@router.get("/version", operation_id="ver")
def api_version(request: Request) -> dict[str, str]:
    """Application version (same payload as legacy ``/version`` / ``/v/version``)."""
    return {
        "version": request.app.version,
        "api_version": API_VERSION,
        "release_version": RELEASE_VERSION,
    }


@router.get("/ping")
def ping():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v2!"})
