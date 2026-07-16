import os
from typing import Any

from fastapi import APIRouter
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

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
    try:
        redis_client = Redis.from_url(
            url,
            password=REDIS_AUTH,
            decode_responses=True,  # Decode responses to UTF-8, if needed
        )
        # Ping the server to check the connection
        response = redis_client.ping()
        print(f"Connected to Redis. Server responded with: {response}")
        return redis_client
    except RedisConnectionError as e:
        print(f"Unable to connect to Redis: {e}")
        return None


redis_client = get_redis_client(REDIS_URL)

# Async client used by routes and lifespan (`import redis` would shadow this name).
redis = redis_client

# Redis acts as a message broker. When a POST request is received, the event is pushed to a Redis channel.
# A background listener consumes events and broadcasts them to WebSocket clients in ws/redis.py


async def publish_event(channel: str = REDIS_EVENT_CHANNEL, event: Any = None):
    await redis.publish(channel, event.json())


async def start_event_listener(channel: str = REDIS_EVENT_CHANNEL):
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    async for message in pubsub.listen():
        if message["type"] == "message":
            await manager.broadcast(message["data"])
