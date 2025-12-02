from typing import Any

import redis
from fastapi import APIRouter
from redis.asyncio import Redis

from nabla.api.demo.socket.ws_manager import manager
from nabla.config_settings import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

REDIS_CHANNEL = "fastapi.sample"
REDIS_EVENT_CHANNEL = REDIS_CHANNEL + ".sensor_events"

REDIS_TASK_QUEUE = ".task_queue."
REDIS_SENSOR_CHANNEL = "sensor"
REDIS_NOTES_CHANNEL = "notes"

router = APIRouter()

# Global variable declaration
# redis: Redis | None = None

# global redis
# redis = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

# redis = Redis(
#     host=REDIS_HOST,
#     port=REDIS_PORT,
#     decode_responses=True,
#     max_connections=96,
# )
# print(redis.get_nodes())

# creds_provider = redis.UsernamePasswordCredentialProvider("default", "redis_password")


def get_redis_client(host="localhost", port=6379, password=None):
    try:
        # Create a connection to the Redis server
        # pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0)
        # redis = redis.Redis(connection_pool=pool, decode_responses=True)
        redis_client = Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,  # Decode responses to UTF-8, if needed
        )

        # Ping the server to check the connection
        response = redis_client.ping()
        print(f"Connected to Redis. Server responded with: {response}")
        return redis_client
    except redis.ConnectionError as e:
        print(f"Unable to connect to Redis: {e}")
        return None


redis_client = get_redis_client(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD.get_secret_value())

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
