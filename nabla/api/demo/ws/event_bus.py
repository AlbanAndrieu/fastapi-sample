from redis.asyncio import Redis

from nabla.api.demo.ws.ws_manager import manager
from nabla.config_settings import REDIS_HOST, REDIS_PORT

#from typing import Any
# import orjson
# from fastapi.encoders import jsonable_encoder
# from fastapi_cache import Coder

REDIS_CHANNEL = "fastapi.sample"
REDIS_EVENT_CHANNEL = REDIS_CHANNEL + ".sensor_events"

# Global variable declaration
# redis: Redis | None = None
# pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0)
# redis = redis.Redis(connection_pool=pool, decode_responses=True)
#redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
redis = Redis(host=REDIS_HOST, port=REDIS_PORT)

# class ORJsonCoder(Coder):
#     @classmethod
#     def encode(cls, value: Any) -> bytes:
#         return orjson.dumps(
#             value,
#             default=jsonable_encoder,
#             option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
#         )

#     @classmethod
#     def decode(cls, value: bytes) -> Any:
#         return orjson.loads(value)


# Redis acts as a message broker. When a POST request is received, the event is pushed to a Redis channel.
# A background listener consumes events and broadcasts them to WebSocket clients in ws/event_bus.py

async def publish_event(event):
    await redis.publish(REDIS_EVENT_CHANNEL, event.json())


async def start_event_listener():
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_EVENT_CHANNEL)
    async for message in pubsub.listen():
        if message["type"] == "message":
            await manager.broadcast(message["data"])
