"""Application lifecycle management (startup/shutdown)."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from nabla.api.db.database import database, init_db
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.utils.logger import logger
from nabla.utils.prometheus import update_system_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    FastAPICache.init(InMemoryBackend())
    app.state.redis = redis
    await database.connect()

    # Initialize databases
    await init_db()
    from nabla.api.notes.models import init_db as init_db_note
    from nabla.api.users.models import init_db as init_db_user

    await init_db_note()
    await init_db_user()
    await init_db_sensor_reading()

    # Start background tasks
    system_metrics_task = asyncio.create_task(update_system_metrics())
    background_tasks = [system_metrics_task]
    if redis is not None:
        background_tasks.append(asyncio.create_task(start_event_listener()))

    logger.info("🚀 Sensor Dashboard started")
    logger.info(f"Initial sensor readings: {len(recent_readings)}")
    logger.info(f"Debug mode: {bool(os.getenv('DEBUG'))}")

    yield

    # Shutdown
    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        with suppress(asyncio.CancelledError):
            await task

    if database:
        await database.disconnect()
    if redis is not None:
        await redis.aclose()

    logger.info("📊 Sensor Dashboard shutting down")
    logger.info(
        f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}"
    )
