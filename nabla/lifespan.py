# ruff: noqa: PLC0415 -- model initialization imports stay lazy to avoid cycles.

"""Application lifecycle management (startup/shutdown)."""

import asyncio
import socket
import time
from collections.abc import Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from nabla.api.db.database import database, db_pool, init_db
from nabla.api.demo.demo import initialize_demo_feature_flags
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import initialize_sensor_demo, metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.api.runtime_topology import runtime_topology_heartbeat
from nabla.config_settings import get_settings
from nabla.mcp.client import close_mcp_clients, initialize_mcp_clients
from nabla.utils.logger import logger
from nabla.utils.prometheus import update_system_metrics


async def _cancel_background_tasks(tasks: list[asyncio.Task[None]]) -> None:
    """Cancel application-owned background tasks before releasing resources."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _report_background_task_result(task: asyncio.Task[None]) -> None:
    """Report unexpected termination without making optional workers fatal."""
    if task.cancelled():
        return

    error = task.exception()
    if error is None:
        logger.warning("background_task_stopped", task_name=task.get_name())
        return

    logger.error(
        "background_task_failed",
        task_name=task.get_name(),
        exception_type=type(error).__name__,
    )


def _start_background_task(
    coroutine: Coroutine[Any, Any, None],
    *,
    name: str,
    tasks: list[asyncio.Task[None]],
) -> None:
    """Start and track one best-effort application background task."""
    task = asyncio.create_task(coroutine, name=name)
    task.add_done_callback(_report_background_task_result)
    tasks.append(task)


@asynccontextmanager
def _startup_database_failure(exc: BaseException) -> tuple[str, str]:
    """Classify critical PostgreSQL startup failures without leaking connection data."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__

    message = " ".join(str(item) for item in chain).casefold()
    if any(isinstance(item, socket.gaierror) for item in chain) or any(
        marker in message
        for marker in (
            "temporary failure in name resolution",
            "name or service not known",
            "getaddrinfo failed",
        )
    ):
        return "dns", "name_resolution"
    if "password authentication failed" in message or "authentication failed" in message:
        return "authentication", "credentials"
    if "connection refused" in message:
        return "connect", "connection_refused"
    if "timeout" in message:
        return "connect", "timeout"
    if "ssl" in message or "certificate" in message:
        return "tls", "tls_error"
    return "database", "connect_failed"


async def _connect_critical_database() -> None:
    """Connect PostgreSQL and emit bounded startup evidence for cloud diagnostics."""
    settings = get_settings()
    started = time.perf_counter()
    logger.info(
        "startup_dependency_begin dependency=postgres critical=true host=%s port=%s db=%s",
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_db,
    )
    try:
        await database.connect()
    except Exception as exc:
        phase, stage = _startup_database_failure(exc)
        logger.error(
            "startup_dependency_failed dependency=postgres critical=true phase=%s stage=%s exception=%s elapsed_ms=%s",
            phase,
            stage,
            exc.__class__.__name__,
            round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "startup_dependency_ready dependency=postgres critical=true elapsed_ms=%s",
        round((time.perf_counter() - started) * 1000),
    )


async def lifespan(app: FastAPI):
    """Acquire application resources safely and unwind partial startup failures."""
    async with AsyncExitStack() as resources:
        resources.callback(db_pool.close)
        FastAPICache.init(InMemoryBackend())
        app.state.redis = redis
        if redis is not None:
            resources.push_async_callback(redis.aclose)

        await _connect_critical_database()
        resources.push_async_callback(database.disconnect)

        logger.info("startup_stage_begin stage=database_schema critical=true")
        schema_started = time.perf_counter()
        try:
            await init_db()
        except Exception as exc:
            logger.error(
                "startup_stage_failed stage=database_schema critical=true exception=%s elapsed_ms=%s",
                exc.__class__.__name__,
                round((time.perf_counter() - schema_started) * 1000),
            )
            raise
        logger.info(
            "startup_stage_ready stage=database_schema critical=true elapsed_ms=%s",
            round((time.perf_counter() - schema_started) * 1000),
        )
        from nabla.api.notes.models import init_db as init_db_note
        from nabla.api.users.models import init_db as init_db_user

        await init_db_note()
        await init_db_user()
        await init_db_sensor_reading()
        initialize_demo_feature_flags()
        initialize_sensor_demo()
        resources.push_async_callback(close_mcp_clients)
        await initialize_mcp_clients()

        background_tasks: list[asyncio.Task[None]] = []
        resources.push_async_callback(_cancel_background_tasks, background_tasks)
        if get_settings().metrics_enabled:
            _start_background_task(
                update_system_metrics(),
                name="system-metrics",
                tasks=background_tasks,
            )
        if redis is not None:
            _start_background_task(
                start_event_listener(),
                name="redis-event-listener",
                tasks=background_tasks,
            )
            _start_background_task(
                runtime_topology_heartbeat(redis),
                name="runtime-topology-heartbeat",
                tasks=background_tasks,
            )

        logger.info("🚀 Sensor Dashboard started")
        logger.info(f"Initial sensor readings: {len(recent_readings)}")
        logger.info("Debug mode: %s", getattr(app, "debug", False))

        yield

        logger.info("📊 Sensor Dashboard shutting down")
        logger.info(
            f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}"
        )
