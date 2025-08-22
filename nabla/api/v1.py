import random
import os

from uuid import uuid4
import redis

from redis.cluster import Redis
from ddtrace.trace import tracer
from fastapi import APIRouter
from starlette.responses import JSONResponse


# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

QUOTES = [
    "Strive not to be a success, but rather to be of value. - Albert Einstein",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
]

router = APIRouter(prefix="/v1")


@router.get("/message")
async def demo_message():
    return {"Hello": "World"}


# Global variable declaration
redis_conn: Redis | None


@router.get("/random")
async def demo_random():
    try:
        global redis_conn  # noqa: PLW0603
        redis_conn = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
        result = redis_conn.get("randomnumber")
        if result is None:
            return str(uuid4())  # Fallback to uuid if key doesn't exist
        return str(result)
    except redis.RedisError:
        return str(uuid4())  # Fallback to uuid on connection error


@router.get("/ping")
async def ping():
    with tracer.trace("get_quote") as span:
        quote = random.choice(QUOTES) + "\n"  # noqa: S311 # nosec
        span.set_tag("quote", quote)
        return quote


@router.get("/pong")
async def pong():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v1!"})
