from fastapi import APIRouter, HTTPException, Request, status
from fastapi_cache.decorator import cache
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from nabla.api.demo.demo import uniform_secret
from nabla.utils.logger import logger
from nabla.utils.prometheus import ERROR_COUNT

router = APIRouter(prefix="/test")


@router.get("/sentry-debug")
def trigger_error():
    pass


@router.get("/invalid")
def invalid():
    try:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid",
        )  # ValueError("Invalid")
    except Exception as ex:
        logger.error(ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid request",
        ) from ex


@router.get("/exception")
def exception():
    try:
        raise ValueError("sadness")
    except Exception as ex:
        logger.error(ex, exc_info=True)
        ERROR_COUNT.labels(ex).inc()
        span = trace.get_current_span()

        # generate random number
        seconds = uniform_secret()

        # record_exception converts the exception into a span event.
        ioexception = IOError("Failed at " + str(seconds))
        span.record_exception(ioexception)
        span.set_attributes({"est": True})
        # Update the span status to failed.
        span.set_status(Status(StatusCode.ERROR, "internal error"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Got sadness",
        ) from ex


@router.get("/env")
def env(req: Request):
    try:
        env = req.scope["env"]
        return {
            "message": "Here is an example of getting an environment variable: " + env.MESSAGE,
        }
    except Exception as ex:
        logger.error(ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Env not available outside of Cloudflare worker",
        ) from ex
    finally:
        logger.info("DONE")


@router.get("/cached")
@cache(expire=60)
async def get_cached_data():
    return {"msg": "This response is cached!"}
