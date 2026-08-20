import inspect
import os
from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis

from nabla.api.demo.socket.ws_manager import manager
from nabla.config_settings import REDIS_URL

REDIS_CHANNEL = "fastapi.sample"
REDIS_EVENT_CHANNEL = REDIS_CHANNEL + ".sensor_events"

REDIS_TASK_QUEUE = ".task_queue."
REDIS_SENSOR_CHANNEL = "sensor"
REDIS_NOTES_CHANNEL = "notes"

router = APIRouter()

# Global variable declaration
# redis: Redis | None = None

# global redis
# redis = redis.StrictRedis.from_url(REDIS_URL)

# redis = Redis.from_url(
#     REDIS_URL,
#     decode_responses=True,
#     max_connections=96,
# )
# print(redis.get_nodes())

# creds_provider = redis.UsernamePasswordCredentialProvider("default", "redis_password")


REDIS_AUTH = os.environ.get("REDIS_AUTH", "")


def get_redis_client(url: str) -> Redis | None:
    """Create the async client; connectivity is checked by the health probe."""
    return Redis.from_url(
        url,
        password=REDIS_AUTH or None,
        decode_responses=True,
        max_connections=int(os.environ.get("REDIS_MAX_CONNECTIONS", "10")),
    )


redis_client = get_redis_client(REDIS_URL)

# Async client used by routes and lifespan (`import redis` would shadow this name).
redis = redis_client

# Redis acts as a message broker. When a POST request is received, the event is pushed to a Redis channel.
# A background listener consumes events and broadcasts them to WebSocket clients in ws/redis.py


async def publish_event(channel: str = REDIS_EVENT_CHANNEL, event: Any = None):
    await redis.publish(channel, event.json())


async def _close_pubsub(pubsub: Any) -> None:
    """Close a Redis PubSub instance across redis-py async API versions."""
    close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def start_event_listener(channel: str = REDIS_EVENT_CHANNEL):
    if redis is None:
        return
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    finally:
        await _close_pubsub(pubsub)
