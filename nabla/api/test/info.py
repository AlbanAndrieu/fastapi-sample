import asyncio
import random

from fastapi import APIRouter, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from nabla.utils.logger import logger
from nabla.utils.prometheus import ERROR_COUNT

router = APIRouter(prefix="/test")


@router.get("/sentry-debug")
async def trigger_error():
    pass


@router.get("/invalid")
async def invalid():
    raise ValueError("Invalid ")


@router.get("/exception")
async def exception():
    try:
        raise ValueError("sadness")
    except Exception as ex:
        logger.error(ex, exc_info=True)
        ERROR_COUNT.labels(ex).inc()
        span = trace.get_current_span()

        # generate random number
        seconds = random.uniform(0, 30)  # nosec  # noqa: S311

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
async def env(req: Request):
    try:
        env = req.scope["env"]
        return {
            "message": "Here is an example of getting an environment variable: "
            + env.MESSAGE,
        }
    except Exception as ex:
        logger.error(ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Env not available outside of Cloudflare worker",
        ) from ex
    finally:
        logger.info("DONE")


@router.get("/users/{user_id}")
async def get_user(user_id: int):
    """
    👤 User endpoint with variable response time
    Simulates database calls with realistic latency
    """
    # Simulate realistic processing time
    await asyncio.sleep(random.uniform(0.1, 0.5))  # nosec #noqa: S311

    # Simulate not found scenarios
    if user_id == 404:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "active": True,
        "created_at": "2024-01-01T00:00:00Z",
    }
