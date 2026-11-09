"""Redis L2 stores ONLY approved anonymous public directory labels."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nabla.api import ui_public_directory_redis as cache
from nabla.api import ui_public_services
from nabla.api.ui_public_services import PublicUiService, PublicUiServices


class MemoryRedis:
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}
        self.ttl: int | None = None

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        self.rows[key] = value
        self.ttl = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.rows.get(key)


def _projection() -> PublicUiServices:
    return PublicUiServices(
        catalogRevision="sha256:" + "a" * 64,
        catalogSource="backstage-v2",
        boardState="fresh",
        services=[
            PublicUiService(name="Gatus", kind="Component", state="ok"),
            PublicUiService(name="TrueNAS", kind="Resource", state="fail"),
        ],
    )


def _enable(monkeypatch, redis: MemoryRedis) -> None:
    monkeypatch.setenv("NABLA_PUBLIC_DIRECTORY_REDIS_ENABLED", "true")
    monkeypatch.setenv(
        "NABLA_PUBLIC_DIRECTORY_REDIS_NAMESPACE", "fastapi-cloud-tests",
    )
    monkeypatch.setattr(cache, "resolve_redis_client", lambda: redis)


@pytest.mark.asyncio
async def test_redis_never_persists_ok_or_owner_evidence(monkeypatch) -> None:
    redis = MemoryRedis()
    _enable(monkeypatch, redis)
    assert await cache.write_public_directory_redis(_projection())
    assert redis.ttl == 300
    assert len(redis.rows) == 1
    raw = next(iter(redis.rows.values()))
    assert '"ok"' not in raw
    assert '"fail"' not in raw
    assert "172.17." not in raw
    assert "token" not in raw.lower()
    data = await cache.read_public_directory_redis()
    assert data is not None
    assert data.boardState == "pending"
    assert data.catalogSource == "bootstrap-snapshot"
    assert all(row.state == "unknown" for row in data.services)


@pytest.mark.asyncio
async def test_redis_requires_enabled_and_namespaced_cache(monkeypatch) -> None:
    redis = MemoryRedis()
    _enable(monkeypatch, redis)
    monkeypatch.delenv("NABLA_PUBLIC_DIRECTORY_REDIS_NAMESPACE")
    assert not await cache.write_public_directory_redis(_projection())
    assert await cache.read_public_directory_redis() is None
    monkeypatch.setenv("NABLA_PUBLIC_DIRECTORY_REDIS_NAMESPACE", "LAN:OTHER")
    assert cache._cache_key() is None
    monkeypatch.delenv("NABLA_PUBLIC_DIRECTORY_REDIS_ENABLED")
    assert await cache.read_public_directory_redis() is None


@pytest.mark.asyncio
async def test_redis_rejects_expired_or_poisoned_envelopes(monkeypatch) -> None:
    redis = MemoryRedis()
    _enable(monkeypatch, redis)
    await cache.write_public_directory_redis(_projection())
    key = next(iter(redis.rows))
    payload = json.loads(redis.rows[key])
    payload["storedAt"] = time.time() - 3600
    redis.rows[key] = json.dumps(payload)
    assert await cache.read_public_directory_redis() is None
    payload["storedAt"] = time.time()
    payload["directory"]["services"][0]["name"] = "172.17.0.24"
    redis.rows[key] = json.dumps(payload)
    assert await cache.read_public_directory_redis() is None


@pytest.mark.asyncio
async def test_redis_errors_are_nonblocking(monkeypatch) -> None:
    class Unavailable:
        async def set(self, *_args, **_kwargs):
            raise ConnectionError("no Redis")
        async def get(self, *_args, **_kwargs):
            raise ConnectionError("no Redis")

    _enable(monkeypatch, Unavailable())
    assert not await cache.write_public_directory_redis(_projection())
    assert await cache.read_public_directory_redis() is None


@pytest.mark.asyncio
async def test_pending_bootstrap_uses_redis_without_fabricating_green(monkeypatch) -> None:
    redis = MemoryRedis()
    _enable(monkeypatch, redis)
    await cache.write_public_directory_redis(_projection())
    monkeypatch.setattr(
        ui_public_services.health_board, "get_health_board_snapshot",
        AsyncMock(return_value={"state": "pending"}),
    )

    def no_bootstrap():
        raise AssertionError("Should use Redis first for pending evidence")

    monkeypatch.setattr(ui_public_services, "packaged_homelab_catalog", no_bootstrap)
    result = await ui_public_services._bootstrap_public_service_directory(None)
    assert result.boardState == "pending"
    assert [row.name for row in result.services] == ["Gatus", "TrueNAS"]
    assert all(row.state == "unknown" for row in result.services)


@pytest.mark.asyncio
async def test_fresh_bootstrap_prefers_current_board_to_old_redis(monkeypatch) -> None:
    redis = MemoryRedis()
    _enable(monkeypatch, redis)
    await cache.write_public_directory_redis(_projection())
    monkeypatch.setattr(
        ui_public_services.health_board, "get_health_board_snapshot",
        AsyncMock(return_value={
            "state": "fresh",
            "homelab": {"services": [{"id": "gatus", "effective_state": "ok"}]},
        }),
    )
    monkeypatch.setattr(
        ui_public_services,
        "packaged_homelab_catalog",
        lambda: SimpleNamespace(services=[
            SimpleNamespace(name="Gatus", service_id="gatus"),
        ]),
    )
    result = await ui_public_services._bootstrap_public_service_directory(None)
    assert result.boardState == "fresh"
    assert result.services[0].state == "ok"
    assert len(result.services) == 1
