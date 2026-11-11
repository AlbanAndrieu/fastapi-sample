"""FastAPI Cloud resource guards: cheap anonymous page, bounded diagnostics."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request

from nabla.api import health_board, ui_public_services
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteV2Entity,
    SiteV2Metadata,
)
from nabla.api.runtime_environment import fastapi_cloud_runtime_detected
import nabla.lifespan as lifespan


def cloud_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/ui/services",
            "headers": [(b"host", b"fastapi-sample.fastapicloud.dev")],
            "scheme": "https",
        },
    )


def local_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/ui/services",
            "headers": [(b"host", b"localhost")],
            "scheme": "http",
        },
    )


def catalog() -> SiteArchitectureCatalogV2:
    return SiteArchitectureCatalogV2(
        catalogRevision="sha256:" + "a" * 64,
        entities=[
            SiteV2Entity(
                kind="Component",
                entityRef="component:default/gatus",
                sourcePath="apps/gatus/catalog-info.yaml",
                metadata=SiteV2Metadata(name="gatus", title="Gatus"),
                spec={},
            ),
        ],
    )


@pytest.mark.asyncio
async def test_cloud_public_landing_never_triggers_health_board_refresh(monkeypatch):
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_CLOUD_PUBLIC_DEEP_PROBES_ENABLED", raising=False)
    await health_board.reset_health_board_cache()
    expensive = AsyncMock(side_effect=AssertionError("unauthorized provider fan-out"))
    monkeypatch.setattr(health_board, "build_health_board_snapshot", expensive)
    monkeypatch.setattr(
        ui_public_services,
        "fetch_site_catalog_v2",
        AsyncMock(return_value=catalog()),
    )
    monkeypatch.setattr(
        ui_public_services,
        "write_public_directory_redis",
        AsyncMock(return_value=False),
    )
    monkeypatch.setitem(ui_public_services._backstage_backoff, "retry_after", 0.0)
    result = await ui_public_services.get_public_ui_services(cloud_request())
    await asyncio.sleep(0)
    assert result.boardState == "pending"
    assert result.services[0].state == "unknown"
    expensive.assert_not_awaited()
    assert health_board._refresh_task is None
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_cached_public_projection_never_copies_secrets(monkeypatch):
    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "_cached_at", time.monotonic())
    monkeypatch.setattr(
        health_board,
        "_cached_snapshot",
        {
            "homelab": {
                "services": [
                    {
                        "id": "gatus",
                        "effective_state": "ok",
                        "probe_stale": False,
                        "secret": "NEVER_ECHO",
                        "url": "https://172.17.0.24/private",
                    },
                ],
            },
            "platform_metrics": {"sensitive": "PRIVATE"},
        },
    )
    result = await health_board.peek_public_health_board_snapshot(cloud_request())
    assert result["state"] == "fresh"
    assert result["homelab"]["services"] == [
        {
            "id": "gatus",
            "effective_state": "ok",
            "probe_stale": False,
        },
    ]
    assert "NEVER_ECHO" not in str(result)
    assert "172.17" not in str(result)
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_cached_board_ttl_is_longer_on_cloud_than_local(monkeypatch):
    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "_cached_snapshot", {"homelab": {"services": []}})
    monkeypatch.setattr(health_board, "_cached_at", time.monotonic() - 70)
    monkeypatch.setattr(health_board, "_ttl_seconds", lambda: 30.0)
    assert (await health_board.peek_public_health_board_snapshot(local_request()))["state"] == "stale"
    assert (await health_board.peek_public_health_board_snapshot(cloud_request()))["state"] == "fresh"
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_cloud_explicit_owner_board_still_starts_a_refresh(monkeypatch):
    await health_board.reset_health_board_cache()
    built = AsyncMock(
        return_value={
            "schema_version": 1,
            "generated_at": "2026-11-09T00:00:00Z",
            "homelab": {"services": []},
        },
    )
    monkeypatch.setattr(health_board, "build_health_board_snapshot", built)
    initial = await health_board.get_health_board_snapshot(cloud_request())
    assert initial["state"] == "pending"
    for _ in range(5):
        await asyncio.sleep(0)
    assert built.await_count == 1
    followup = await health_board.get_health_board_snapshot(cloud_request())
    assert followup["state"] == "fresh"
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_failed_cloud_refresh_backoff_blocks_repeated_provider_work(monkeypatch):
    await health_board.reset_health_board_cache()
    # #406's mechanism: a failed Cloud refresh sets the next allowed attempt.
    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: True)
    monkeypatch.setattr(
        health_board,
        "_next_refresh_allowed_at",
        time.monotonic() + 180.0,
    )
    monkeypatch.setattr(
        health_board,
        "_last_refresh_error",
        "health board refresh deadline exceeded",
    )
    built = AsyncMock(side_effect=AssertionError("must not retry immediately"))
    monkeypatch.setattr(health_board, "build_health_board_snapshot", built)
    for _ in range(3):
        result = await health_board.get_health_board_snapshot(cloud_request())
        assert result["state"] == "pending"
        assert result["retry_after_seconds"] >= 120
    built.assert_not_awaited()
    assert health_board._refresh_task is None
    await health_board.reset_health_board_cache()


def test_cloud_detection_uses_managed_deployment_id(monkeypatch):
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.setenv("FASTAPI_ENV", "development")
    assert fastapi_cloud_runtime_detected() is True


def test_cloud_background_workers_do_not_start_on_replicas(monkeypatch):
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD_BACKGROUND_WORKERS_ENABLED", raising=False)
    assert lifespan.cloud_background_workers_allowed() is False
    start = AsyncMock()
    monkeypatch.setattr(lifespan, "_start_background_task", start)
    lifespan._start_background_workers(
        SimpleNamespace(observability=True, redis=True),
        SimpleNamespace(),
        [],
    )
    start.assert_not_awaited()


def test_cloud_workers_may_be_explicitly_enabled_without_affecting_homelab(monkeypatch):
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.setenv("FASTAPI_CLOUD_BACKGROUND_WORKERS_ENABLED", "true")
    assert lifespan.cloud_background_workers_allowed() is True
    monkeypatch.setenv("FASTAPI_CLOUD_BACKGROUND_WORKERS_ENABLED", "false")
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    assert lifespan.cloud_background_workers_allowed() is True


def test_cloud_disabled_gauges_report_unobserved_not_zero(monkeypatch):
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD_BACKGROUND_WORKERS_ENABLED", raising=False)
    gauges = [Mock(), Mock(), Mock()]
    for attr, gauge in zip(
        ("CPU_USAGE", "MEMORY_USAGE", "PROCESS_MEMORY_RSS"),
        gauges,
        strict=True,
    ):
        monkeypatch.setattr(lifespan, attr, gauge)
    lifespan._start_background_workers(
        SimpleNamespace(observability=True),
        SimpleNamespace(),
        [],
    )
    for gauge in gauges:
        gauge.set.assert_called_once()
        assert str(gauge.set.call_args.args[0]).lower() == "nan"


def test_cloud_profiler_sampling_is_disabled_by_default(monkeypatch):
    from nabla.app_factory import cloud_profiling_allowed

    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD_PROFILING_ENABLED", raising=False)
    assert cloud_profiling_allowed() is False


def test_cloud_profiler_sampling_requires_explicit_opt_in(monkeypatch):
    from nabla.app_factory import cloud_profiling_allowed

    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.setenv("FASTAPI_CLOUD_PROFILING_ENABLED", "true")
    assert cloud_profiling_allowed() is True
    monkeypatch.setenv("FASTAPI_CLOUD_PROFILING_ENABLED", "false")
    assert cloud_profiling_allowed() is False


def test_truenas_profiler_policy_is_unchanged(monkeypatch):
    from nabla.app_factory import cloud_profiling_allowed

    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_CLOUD_PROFILING_ENABLED", raising=False)
    assert cloud_profiling_allowed() is True


def test_cloud_profiler_gate_does_not_import_profiler_dependencies(monkeypatch):
    from contextlib import AsyncExitStack
    from nabla import app_factory

    monkeypatch.setenv("FASTAPICLOUD_DEPLOYMENT_ID", "deployment-test")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("FASTAPI_CLOUD_PROFILING_ENABLED", raising=False)
    # Any profiler import would be a regression in cold-start resource usage.
    import builtins
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"nabla.utils.datadog_config", "nabla.utils.pyroscope_config"}:
            raise AssertionError("Cloud should not import profiler modules")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with AsyncExitStack() as stack:
        app_factory._enter_profilers(stack)
