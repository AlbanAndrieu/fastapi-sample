import random

from fastapi import APIRouter
# from redis.cluster import Redis
from starlette.responses import JSONResponse

from nabla.config_settings import DD_TRACE_ENABLED
from nabla.utils.datadog_config import datadog_trace
from nabla.utils.logger import logger

# from fastapi_cache.decorator import cache


QUOTES = [
    "Strive not to be a success, but rather to be of value. - Albert Einstein",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
]

router = APIRouter(prefix="/v1")


@router.get("/ping")
def ping():
    with datadog_trace(enabled=DD_TRACE_ENABLED, name="get_quote") as span:
        logger.info("get random quotes")
        quote = random.choice(QUOTES) + "\n"  # noqa: S311 # nosec
        if span is not None:
            span.set_tag("quote", quote)
        return quote


@router.get("/pong")
def pong():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v1!"})
