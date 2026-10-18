# ruff: noqa: PLC0415 -- model initialization imports stay lazy to avoid cycles.

"""Application lifecycle management (startup/shutdown)."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from redis.exceptions import ConnectionError as RedisConnectionError

from nabla.api.db.database import database, db_pool, init_db
from nabla.api.demo.demo import initialize_demo_feature_flags
from nabla.api.demo.models import init_db as init_db_sensor_reading
from nabla.api.demo.models import recent_readings
from nabla.api.demo.sensor import initialize_sensor_demo, metrics
from nabla.api.demo.socket.redis import redis, start_event_listener
from nabla.api.runtime_topology import runtime_topology_heartbeat
from nabla.app_features import AppFeatures
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
    if isinstance(error, (RedisConnectionError, OSError)):
        # Redis is optional: an unreachable server degrades the worker only.
        logger.warning(
            "background_task_degraded",
            task_name=task.get_name(),
            exception_type=type(error).__name__,
        )
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


async def _connect_critical_database(*, critical: bool = True) -> None:
    """Connect PostgreSQL and emit bounded startup evidence for cloud diagnostics."""
    settings = get_settings()
    started = time.perf_counter()
    logger.info(
        "startup_dependency_begin dependency=postgres critical=%s host=%s port=%s db=%s",
        str(critical).lower(),
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_db,
    )
    try:
        await database.connect()
    except Exception as exc:
        phase, stage = _startup_database_failure(exc)
        # Optional: the single warning is `startup_dependency_degraded`.
        log = logger.error if critical else logger.info
        log(
            "startup_dependency_failed dependency=postgres critical=%s phase=%s stage=%s exception=%s elapsed_ms=%s",
            str(critical).lower(),
            phase,
            stage,
            exc.__class__.__name__,
            round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "startup_dependency_ready dependency=postgres critical=%s elapsed_ms=%s",
        str(critical).lower(),
        round((time.perf_counter() - started) * 1000),
    )


async def _start_critical_database(resources: AsyncExitStack, *, critical: bool = True) -> None:
    """Connect PostgreSQL, register its release and initialize the schema."""
    await _connect_critical_database(critical=critical)
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


def postgres_required() -> bool:
    """Fail fast where PostgreSQL is required (TrueNAS homelab or ``POSTGRES_REQUIRED=true``)."""
    from nabla.api.health_contracts import required_dependencies

    return "postgres" in required_dependencies()


async def _start_database(resources: AsyncExitStack) -> bool:
    """Start PostgreSQL; when optional, degrade instead of aborting startup."""
    if postgres_required():
        await _start_critical_database(resources)
        return True
    try:
        async with AsyncExitStack() as attempt:
            await _start_critical_database(attempt, critical=False)
            resources.push_async_exit(attempt.pop_all())
    except Exception as exc:
        logger.warning(
            "startup_dependency_degraded dependency=postgres critical=false exception=%s hint=%s",
            exc.__class__.__name__,
            "set POSTGRES_REQUIRED=true to fail fast",
        )
        return False
    return True


def build_lifespan(features: AppFeatures | None = None) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build the application lifespan for an explicit set of subsystems.

    PostgreSQL and Redis are optional: an unreachable server degrades the app
    (DB routes answer 503, /readyz reports ``degraded``) unless
    ``POSTGRES_REQUIRED``/``REDIS_REQUIRED`` make them required.
    """
    selected = features or AppFeatures()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Acquire application resources safely and unwind partial startup failures."""
        async with AsyncExitStack() as resources:
            if selected.database:
                resources.callback(db_pool.close)
            FastAPICache.init(InMemoryBackend())
            redis_client = redis if selected.redis else None
            app.state.redis = redis_client
            if redis_client is not None:
                resources.push_async_callback(redis_client.aclose)

            app.state.database_available = False
            if selected.database:
                app.state.database_available = await _start_database(resources)
            else:
                logger.warning("startup_dependency_skipped dependency=postgres critical=false reason=feature_disabled")
            initialize_demo_feature_flags()
            initialize_sensor_demo()
            if selected.mcp:
                resources.push_async_callback(close_mcp_clients)
                await initialize_mcp_clients()

            background_tasks: list[asyncio.Task[None]] = []
            resources.push_async_callback(_cancel_background_tasks, background_tasks)
            _start_background_workers(selected, redis_client, background_tasks)

            logger.info("🚀 Sensor Dashboard started")
            logger.info(f"Initial sensor readings: {len(recent_readings)}")
            logger.info("Debug mode: %s", getattr(app, "debug", False))

            yield

            logger.info("📊 Sensor Dashboard shutting down")
            logger.info(
                f"Final metrics - Connections: {metrics.connection_count}, Requests: {metrics.total_requests}",
            )

    return lifespan


def _start_background_workers(
    features: AppFeatures,
    redis_client: Any,
    tasks: list[asyncio.Task[None]],
) -> None:
    """Start the best-effort workers owned by the enabled subsystems."""
    if features.observability and get_settings().metrics_enabled:
        _start_background_task(
            update_system_metrics(),
            name="system-metrics",
            tasks=tasks,
        )
    if redis_client is not None:
        _start_background_task(
            start_event_listener(),
            name="redis-event-listener",
            tasks=tasks,
        )
        _start_background_task(
            runtime_topology_heartbeat(redis_client),
            name="runtime-topology-heartbeat",
            tasks=tasks,
        )


# Production lifespan (all subsystems enabled), kept for existing callers.
lifespan = build_lifespan()
