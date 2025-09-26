# worker.py
import asyncio
import json

from notes_handler import handle_note

from nabla.api.demo.socket.redis import (
    REDIS_CHANNEL,
    REDIS_NOTES_CHANNEL,
    REDIS_TASK_QUEUE,
    redis,
)
from nabla.utils.logger import logger


async def worker_loop():
    while True:
        note_data = redis.blpop(REDIS_CHANNEL + REDIS_TASK_QUEUE + REDIS_NOTES_CHANNEL, timeout=5)
        if note_data:
            _, note_json = note_data
            note = json.loads(note_json)
            logger.info(f"Processing note {note['id']}")
            try:
              await handle_note(note)
            except Exception as e:
              logger.error(f"Note {note['id']} failed: {e}")
              redis.rpush(REDIS_CHANNEL + REDIS_TASK_QUEUE + "retry_queue", json.dumps(note))
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(worker_loop())
