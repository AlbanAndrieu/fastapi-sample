from fastapi import APIRouter
from redis.asyncio import Redis

from nabla.api.demo.socket.ws_manager import manager
from nabla.config_settings import REDIS_HOST, REDIS_PORT

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


# pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0)
# redis = redis.Redis(connection_pool=pool, decode_responses=True)
redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# Redis acts as a message broker. When a POST request is received, the event is pushed to a Redis channel.
# A background listener consumes events and broadcasts them to WebSocket clients in ws/redis.py


async def publish_event(event):
    await redis.publish(REDIS_EVENT_CHANNEL, event.json())


async def start_event_listener():
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_EVENT_CHANNEL)
    async for message in pubsub.listen():
        if message["type"] == "message":
            await manager.broadcast(message["data"])
