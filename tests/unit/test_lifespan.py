"""Deterministic lifecycle coverage without external services."""

import asyncio
import socket
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import nabla.lifespan as lifecycle
from nabla.api import health_contracts

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
    monkeypatch.setattr(lifecycle, "initialize_demo_feature_flags", Mock())
    monkeypatch.setattr(lifecycle, "initialize_sensor_demo", Mock())
    monkeypatch.setattr(lifecycle, "initialize_mcp_clients", AsyncMock())
    monkeypatch.setattr(lifecycle, "close_mcp_clients", AsyncMock())
    monkeypatch.setattr(
        lifecycle,
        "get_settings",
        lambda: SimpleNamespace(
            metrics_enabled=True,
            postgres_host="postgres.example.test",
            postgres_port=5432,
            postgres_db="postgres",
        ),
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
    lifecycle.initialize_demo_feature_flags.assert_called_once_with()
    lifecycle.initialize_sensor_demo.assert_called_once_with()
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
        raise RuntimeError("listener bug")

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
        exception_type="RuntimeError",
    )


async def test_unreachable_optional_redis_degrades_worker_with_warning(
    monkeypatch,
) -> None:
    logger = Mock()
    monkeypatch.setattr(lifecycle, "logger", logger)
    tasks: list[asyncio.Task[None]] = []
    reported = asyncio.Event()
    logger.warning.side_effect = lambda *args, **kwargs: reported.set()

    async def fail() -> None:
        raise lifecycle.RedisConnectionError("Error 61 connecting to 127.0.0.1:6379")

    lifecycle._start_background_task(fail(), name="redis-event-listener", tasks=tasks)
    await asyncio.wait_for(reported.wait(), timeout=1)
    await lifecycle._cancel_background_tasks(tasks)

    logger.error.assert_not_called()
    logger.warning.assert_called_once_with(
        "background_task_degraded",
        task_name="redis-event-listener",
        exception_type="ConnectionError",
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (socket.gaierror(-3, "Temporary failure in name resolution"), ("dns", "name_resolution")),
        (ConnectionRefusedError("connection refused"), ("connect", "connection_refused")),
        (TimeoutError("connection timeout"), ("connect", "timeout")),
        (RuntimeError("password authentication failed"), ("authentication", "credentials")),
    ],
)
def test_startup_database_failure_classification(error, expected) -> None:
    assert lifecycle._startup_database_failure(error) == expected


async def test_database_dns_failure_remains_startup_fatal_when_required(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_REQUIRED", "true")
    app, resources = _configure_lifecycle(monkeypatch)
    resources["database"].connect.side_effect = socket.gaierror(
        -3,
        "Temporary failure in name resolution",
    )
    logger = Mock()
    monkeypatch.setattr(lifecycle, "logger", logger)

    with pytest.raises(socket.gaierror):
        async with lifecycle.lifespan(app):
            pytest.fail("critical PostgreSQL failure must prevent readiness")

    logger.error.assert_called_once()
    assert "phase=%s stage=%s" in logger.error.call_args.args[0]
    assert logger.error.call_args.args[1:4] == ("true", "dns", "name_resolution")
    resources["database"].disconnect.assert_not_awaited()
    resources["db_pool"].close.assert_called_once()


async def test_optional_database_failure_degrades_without_aborting_startup(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_REQUIRED", raising=False)
    app, resources = _configure_lifecycle(monkeypatch)
    resources["database"].connect.side_effect = ConnectionRefusedError("connection refused")
    logger = Mock()
    monkeypatch.setattr(lifecycle, "logger", logger)

    async with lifecycle.lifespan(app):
        assert app.state.database_available is False

    degraded = [call for call in logger.warning.call_args_list if "startup_dependency_degraded" in call.args[0]]
    assert len(degraded) == 1
    assert degraded[0].args[1] == "ConnectionRefusedError"
    resources["database"].disconnect.assert_not_awaited()
    resources["db_pool"].close.assert_called_once()


async def test_optional_database_success_keeps_disconnect_on_shutdown(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_REQUIRED", raising=False)
    app, resources = _configure_lifecycle(monkeypatch)

    async with lifecycle.lifespan(app):
        assert app.state.database_available is True
        resources["database"].disconnect.assert_not_awaited()

    resources["database"].disconnect.assert_awaited_once()


async def test_homelab_runtime_keeps_postgres_startup_fatal(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_REQUIRED", raising=False)
    monkeypatch.setattr(health_contracts, "runtime_mode", lambda: "homelab")
    app, resources = _configure_lifecycle(monkeypatch)
    resources["database"].connect.side_effect = ConnectionRefusedError("connection refused")
    monkeypatch.setattr(lifecycle, "logger", Mock())

    with pytest.raises(ConnectionRefusedError):
        async with lifecycle.lifespan(app):
            pytest.fail("TrueNAS requires PostgreSQL at startup")


async def test_fastapi_cloud_runtime_does_not_require_postgres(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_REQUIRED", raising=False)
    monkeypatch.setattr(health_contracts, "runtime_mode", lambda: "fastapi_cloud")

    assert lifecycle.postgres_required() is False
