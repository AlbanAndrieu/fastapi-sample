import random
import secrets
from typing import Optional
from uuid import uuid4

from fastapi_cache.decorator import cache
from fastapi import APIRouter
from redis.exceptions import RedisError

# from fastapi_mail import FastMail, MessageSchema, MessageType

from nabla.api.demo.socket.redis import REDIS_CHANNEL, redis
from nabla.auth.controller import AuthController
from nabla.utils.logger import logger
from nabla.utils.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

router = APIRouter()

POOL = list(range(1, 7))
SIZE = 4


def string_secret():
    return random.sample(POOL, SIZE)  # nosec


def uniform_secret():
    return secrets.randbelow(30)
    # return random.uniform(0, 3)  # nosec


@cache()
@router.get("/demo/random")
async def demo_random():
    try:
        # global redis
        # Redis client: nabla.api.demo.socket.redis (REDIS_URL from settings)
        secret = uniform_secret()

        # Validate interval (don't let users sleep for too long)
        secret = max(1, min(secret, 10))  # Between 1-10 seconds

        logger.info(f"set random number {secret} to redis")
        await redis.set(REDIS_CHANNEL + ".randomnumber", secret)
        logger.info(f"get random number {secret} from redis")
        result = await redis.get(REDIS_CHANNEL + ".randomnumber")
        if result is None:
            return str(uuid4())  # Fallback to uuid if key doesn't exist
        return str(result)
    except RedisError:
        return str(uuid4())  # Fallback to uuid on connection error


@router.get("/demo/items/{item_id}")
async def read_item(item_id: int, q: Optional[str] = None):
    logger.info(f"Get items : {item_id}")  # [logging-fstring-interpolation]

    # Validate interval (don't let users sleep for too long)
    item_id = max(1, min(item_id, 10))  # Between 1-10 seconds

    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/items/{item_id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/items/{item_id}").observe(0.1)

    # Example of storing data in Redis
    await redis.set(f"{REDIS_CHANNEL}.item_{item_id}", q or "No Query")

    # yield cached_value

    if item_id % 5 == 0:
        # mock io - wait for x seconds
        # seconds = uniform_secret()
        seconds = item_id
        logger.info(f"Sleeping for {seconds} seconds")

        # asyncio.sleep(seconds)
        # await asyncio.sleep(seconds)
        # await run_in_threadpool(time.sleep, seconds)

    cached_value = await redis.get(f"{REDIS_CHANNEL}.item_{item_id}")

    if cached_value is None:
        logger.info(f"Cached value is None for item_id: {item_id}")
        cached_value = "None"

    return {"item_id": item_id, "q": cached_value}


@router.get("/demo/auth")
def root():
    logger.info("Hello")
    """
    Root endpoint that provides a welcome message and documentation link.
    """
    return AuthController.read_root()


# @router.post("/demo/email")
# async def simple_send(email: EmailSchema) -> JSONResponse:
#     html = """<p>Hi this test mail, thanks for using Fastapi-mail</p> """

#     message = MessageSchema(
#         subject="Fastapi-Mail module",
#         recipients=email.dict().get("email"),
#         body=html,
#         subtype=MessageType.html,
#     )

#     fm = FastMail(conf)
#     await fm.send_message(message)
#     return JSONResponse(status_code=200, content={"message": "email has been sent"})
