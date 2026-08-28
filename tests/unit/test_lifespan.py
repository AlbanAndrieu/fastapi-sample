"""Deterministic lifecycle coverage without external services."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import nabla.lifespan as lifecycle

pytestmark = pytest.mark.asyncio


def _startup_module(name: str, init_db: AsyncMock) -> ModuleType:
    module = ModuleType(name)
    module.init_db = init_db
    return module


def _configure_lifecycle(monkeypatch) -> tuple[SimpleNamespace, dict[str, object]]:
    database = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    db_pool = SimpleNamespace(close=Mock())
    redis = SimpleNamespace(aclose=AsyncMock())
    init_db_note = AsyncMock()
    init_db_user = AsyncMock()
    stopped: set[str] = set()

    async def background_task(name: str) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            stopped.add(name)

    monkeypatch.setattr(lifecycle, "database", database)
    monkeypatch.setattr(lifecycle, "db_pool", db_pool)
    monkeypatch.setattr(lifecycle, "redis", redis)
    monkeypatch.setattr(lifecycle.FastAPICache, "init", Mock())
    monkeypatch.setattr(lifecycle, "init_db", AsyncMock())
    monkeypatch.setattr(lifecycle, "init_db_sensor_reading", AsyncMock())
    monkeypatch.setattr(lifecycle, "initialize_mcp_clients", AsyncMock())
    monkeypatch.setattr(lifecycle, "close_mcp_clients", AsyncMock())
    monkeypatch.setattr(
        lifecycle,
        "get_settings",
        lambda: SimpleNamespace(metrics_enabled=True),
    )
    monkeypatch.setattr(
        lifecycle,
        "update_system_metrics",
        lambda: background_task("system-metrics"),
    )
    monkeypatch.setattr(
        lifecycle,
        "start_event_listener",
        lambda: background_task("redis-event-listener"),
    )
    monkeypatch.setitem(
        sys.modules,
        "nabla.api.notes.models",
        _startup_module("nabla.api.notes.models", init_db_note),
    )
    monkeypatch.setitem(
        sys.modules,
        "nabla.api.users.models",
        _startup_module("nabla.api.users.models", init_db_user),
    )

    app = SimpleNamespace(state=SimpleNamespace())
    resources = {
        "database": database,
        "db_pool": db_pool,
        "redis": redis,
        "init_db_note": init_db_note,
        "init_db_user": init_db_user,
        "stopped": stopped,
    }
    return app, resources


async def test_lifespan_releases_resources_after_normal_shutdown(monkeypatch) -> None:
    app, resources = _configure_lifecycle(monkeypatch)

    async with lifecycle.lifespan(app):
        await asyncio.sleep(0)
        task_names = {task.get_name() for task in asyncio.all_tasks()}
        assert {"system-metrics", "redis-event-listener"} <= task_names
        assert app.state.redis is resources["redis"]

    resources["database"].disconnect.assert_awaited_once()
    resources["redis"].aclose.assert_awaited_once()
    resources["db_pool"].close.assert_called_once()
    lifecycle.close_mcp_clients.assert_awaited_once()
    assert resources["stopped"] == {"system-metrics", "redis-event-listener"}


async def test_lifespan_rolls_back_partial_startup(monkeypatch) -> None:
    app, resources = _configure_lifecycle(monkeypatch)
    lifecycle.initialize_mcp_clients.side_effect = RuntimeError("MCP unavailable")

    with pytest.raises(RuntimeError, match="MCP unavailable"):
        async with lifecycle.lifespan(app):
            pytest.fail("startup failure must prevent request handling")

    resources["database"].disconnect.assert_awaited_once()
    resources["redis"].aclose.assert_awaited_once()
    resources["db_pool"].close.assert_called_once()
    lifecycle.close_mcp_clients.assert_awaited_once()
    assert resources["stopped"] == set()


async def test_lifespan_releases_resources_when_serving_task_is_cancelled(
    monkeypatch,
) -> None:
    app, resources = _configure_lifecycle(monkeypatch)
    entered = asyncio.Event()

    async def serve() -> None:
        async with lifecycle.lifespan(app):
            entered.set()
            await asyncio.Event().wait()

    serving_task = asyncio.create_task(serve())
    await entered.wait()
    await asyncio.sleep(0)
    serving_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await serving_task

    resources["database"].disconnect.assert_awaited_once()
    resources["redis"].aclose.assert_awaited_once()
    resources["db_pool"].close.assert_called_once()
    lifecycle.close_mcp_clients.assert_awaited_once()
    assert resources["stopped"] == {"system-metrics", "redis-event-listener"}


async def test_failed_background_task_is_reported_and_does_not_break_cleanup(
    monkeypatch,
) -> None:
    logger = Mock()
    monkeypatch.setattr(lifecycle, "logger", logger)
    tasks: list[asyncio.Task[None]] = []
    reported = asyncio.Event()
    logger.error.side_effect = lambda *args, **kwargs: reported.set()

    async def fail() -> None:
        raise ConnectionError("listener unavailable")

    lifecycle._start_background_task(
        fail(),
        name="redis-event-listener",
        tasks=tasks,
    )
    await asyncio.wait_for(reported.wait(), timeout=1)
    await lifecycle._cancel_background_tasks(tasks)

    logger.error.assert_called_once_with(
        "background_task_failed",
        task_name="redis-event-listener",
        exception_type="ConnectionError",
    )
