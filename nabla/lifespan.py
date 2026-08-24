"""Application lifecycle management (startup/shutdown)."""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from nabla.api.db.database import database, db_pool, init_db
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.config_settings import get_settings
from nabla.mcp.client import close_mcp_clients, initialize_mcp_clients
from nabla.utils.logger import logger
from nabla.utils.prometheus import update_system_metrics


async def _cancel_background_tasks(tasks: list[asyncio.Task]) -> None:
    """Cancel application-owned background tasks before releasing resources."""
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Acquire application resources safely and unwind partial startup failures."""
    async with AsyncExitStack() as resources:
        resources.callback(db_pool.close)
        FastAPICache.init(InMemoryBackend())
        app.state.redis = redis
        if redis is not None:
            resources.push_async_callback(redis.aclose)

        await database.connect()
        resources.push_async_callback(database.disconnect)

        await init_db()
        from nabla.api.notes.models import init_db as init_db_note
        from nabla.api.users.models import init_db as init_db_user

        await init_db_note()
        await init_db_user()
        await init_db_sensor_reading()
        resources.push_async_callback(close_mcp_clients)
        await initialize_mcp_clients()

        background_tasks: list[asyncio.Task] = []
        resources.push_async_callback(_cancel_background_tasks, background_tasks)
        if get_settings().metrics_enabled:
            background_tasks.append(
                asyncio.create_task(update_system_metrics(), name="system-metrics")
            )
        if redis is not None:
            background_tasks.append(
                asyncio.create_task(start_event_listener(), name="redis-event-listener")
            )

        logger.info("🚀 Sensor Dashboard started")
        logger.info(f"Initial sensor readings: {len(recent_readings)}")
        logger.info(f"Debug mode: {bool(os.getenv('DEBUG'))}")

        yield

        logger.info("📊 Sensor Dashboard shutting down")
        logger.info(
            f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}"
        )
