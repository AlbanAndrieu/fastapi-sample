from fastapi import APIRouter
from starlette.responses import JSONResponse

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

router = APIRouter(prefix="/v2")


@router.get("/ping")
def ping():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v2!"})
