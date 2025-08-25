import os
import random
from uuid import uuid4

import redis
from ddtrace.trace import tracer
from fastapi import APIRouter

# from redis.cluster import Redis
from starlette.responses import JSONResponse

from nabla.utils.logger import logger

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
    logger.info("demo_message")
    return {"Hello": "World"}


# Global variable declaration
# redis_conn: Redis | None
redis_conn = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

POOL = list(range(1, 7))
SIZE = 4


def string_secret():
    return random.sample(POOL, SIZE)  # nosec


def uniform_secret():
    return random.uniform(0, 3)  # nosec # noqa: S311


@router.get("/random")
async def demo_random():
    try:
        # global redis_conn
        # redis_conn = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
        secret = uniform_secret()

        # Validate interval (don't let users sleep for too long)
        secret = max(1, min(secret, 10))  # Between 1-10 seconds

        logger.info(f"set random number {secret} to redis")
        redis_conn.set("randomnumber", secret)
        logger.info(f"get random number {secret} from redis")
        result = redis_conn.get("randomnumber")
        if result is None:
            return str(uuid4())  # Fallback to uuid if key doesn't exist
        return str(result)
    except redis.RedisError:
        return str(uuid4())  # Fallback to uuid on connection error


@router.get("/ping")
async def ping():
    with tracer.trace("get_quote") as span:
        logger.info("get random quotes")
        quote = random.choice(QUOTES) + "\n"  # noqa: S311 # nosec
        span.set_tag("quote", quote)
        return quote


@router.get("/pong")
async def pong():
    """
    Healthcheck endpoint.
    """
    return JSONResponse({"ping": "pong v1!"})
