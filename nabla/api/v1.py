import random

# import redis
from ddtrace.trace import tracer
from fastapi import APIRouter
from fastapi_cache.decorator import cache
from slowapi import Limiter
from slowapi.util import get_remote_address

# from redis.cluster import Redis
from starlette.responses import JSONResponse

from nabla.utils.logger import logger

# from fastapi_cache.decorator import cache


QUOTES = [
    "Strive not to be a success, but rather to be of value. - Albert Einstein",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
]

router = APIRouter(prefix="/v1")
limiter = Limiter(key_func=get_remote_address)


@cache(expire=60)
@router.get("/message")
def demo_message():
    logger.info("demo_message")
    return {"Hello": "World"}


@router.get("/ping")
def ping():
    with tracer.trace("get_quote") as span:
        logger.info("get random quotes")
        quote = random.choice(QUOTES) + "\n"  # noqa: S311 # nosec
        span.set_tag("quote", quote)
        return quote


@router.get("/pong")
def pong():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v1!"})
