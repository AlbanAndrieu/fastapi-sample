"""Cloud resource-budget regression tests: no uncontrolled probe refreshes."""

from __future__ import annotations

import asyncio
import time

import pytest
from starlette.requests import Request

from nabla.api import health_board
from nabla.settings.health_runtime import HealthRuntimeSettings


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/health-board",
        "headers": [],
    })


def test_cloud_health_board_cache_ttl_does_not_modify_homelab(monkeypatch) -> None:
    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: True)
    assert health_board._ttl_seconds() == 180.0
    assert health_board._failure_backoff_seconds() == 90.0

    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: False)
    assert health_board._ttl_seconds() == 30.0
    assert health_board._failure_backoff_seconds() == 0.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", 180.0),
        ("nan", 180.0),
        ("1", 60.0),
        ("999999", 600.0),
        ("240", 240.0),
    ],
)
def test_cloud_cache_ttl_bounds(value: str, expected: float) -> None:
    assert HealthRuntimeSettings(
        cloud_health_board_cache_ttl_seconds=value,
    ).cloud_health_board_cache_ttl_seconds == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("invalid", 90.0),
        ("inf", 90.0),
        ("1", 15.0),
        ("9999", 300.0),
    ],
)
def test_cloud_failure_backoff_bounds(value: str, expected: float) -> None:
    assert HealthRuntimeSettings(
        cloud_health_board_failure_backoff_seconds=value,
    ).cloud_health_board_failure_backoff_seconds == expected


@pytest.mark.asyncio
async def test_cloud_pending_singleflight_cannot_start_again_during_warmup(
    monkeypatch,
) -> None:
    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: True)
    release = asyncio.Event()
    counter = 0

    async def build(_request: Request) -> dict:
        nonlocal counter
        counter += 1
        await release.wait()
        return {"schema_version": 1, "homelab": {"services": []}}

    monkeypatch.setattr(health_board, "build_health_board_snapshot", build)
    for _ in range(12):
        response = await health_board.get_health_board_snapshot(_request())
        assert response["state"] == "pending"
    await asyncio.sleep(0)
    assert counter == 1

    release.set()
    for _ in range(8):
        await asyncio.sleep(0)
    cached = await health_board.get_health_board_snapshot(_request())
    assert cached["state"] == "fresh"
    for _ in range(8):
        await health_board.get_health_board_snapshot(_request(), force_refresh=True)
    assert counter == 1
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_cloud_failed_refresh_respects_retry_backoff(monkeypatch) -> None:
    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: True)
    runs = 0

    async def fail(_request: Request) -> dict:
        nonlocal runs
        runs += 1
        raise RuntimeError("synthetic provider failure for test")

    monkeypatch.setattr(health_board, "build_health_board_snapshot", fail)
    await health_board.get_health_board_snapshot(_request())
    for _ in range(4):
        await asyncio.sleep(0)
    for _ in range(10):
        pending = await health_board.get_health_board_snapshot(_request())
        assert pending["state"] == "pending"
        assert pending["retry_after_seconds"] >= 2
    assert runs == 1
    assert health_board._next_refresh_allowed_at > time.monotonic()
    await health_board.reset_health_board_cache()


@pytest.mark.asyncio
async def test_homelab_keeps_existing_refresh_semantics(monkeypatch) -> None:
    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "_cloud_budget_enabled", lambda: False)
    runs = 0

    async def build(_request: Request) -> dict:
        nonlocal runs
        runs += 1
        return {"schema_version": 1, "homelab": {"services": []}}

    monkeypatch.setattr(health_board, "build_health_board_snapshot", build)
    await health_board.get_health_board_snapshot(_request())
    for _ in range(6):
        await asyncio.sleep(0)
    assert runs == 1
    await health_board.get_health_board_snapshot(_request(), force_refresh=True)
    for _ in range(6):
        await asyncio.sleep(0)
    assert runs == 2
    await health_board.reset_health_board_cache()


def test_background_host_metrics_sampling_rate(monkeypatch) -> None:
    from nabla.api.runtime_environment import fastapi_cloud_runtime_detected
    from nabla.utils import prometheus

    # Keep explicit Cloud and LAN semantics; never infer by raw IP.
    monkeypatch.setenv("FASTAPI_CLOUD", "true")
    monkeypatch.delenv("FASTAPI_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("FASTAPI_ENV", raising=False)
    assert fastapi_cloud_runtime_detected()
    assert prometheus.system_metrics_interval_seconds() == 30.0

    monkeypatch.delenv("FASTAPI_CLOUD")
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    assert prometheus.system_metrics_interval_seconds() == 5.0


def test_cloud_domain_recognized_without_loose_lan_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_DOMAIN", "fastapi-sample.fastapicloud.dev")
    monkeypatch.setenv("FASTAPI_ENV", "development")
    assert health_board._cloud_budget_enabled()

    monkeypatch.setenv("APP_DOMAIN", "sample.albandrieu.com")
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    assert not health_board._cloud_budget_enabled()
