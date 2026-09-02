"""Tests for the best-effort L1 + Redis L2 external probe cache."""

import json

import pytest

from nabla.api import external_probe_cache as cache
from nabla.api.external_probe_cache import ProbeCachePolicy


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, nx=False, ex=None):
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, _script: str, _numkeys: int, key: str, token: str):
        if self.values.get(key) != token:
            return 0
        self.values.pop(key, None)
        return 1

    async def delete(self, *keys: str):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)


class FailingRedis(FakeRedis):
    async def get(self, key: str):
        del key
        raise ConnectionError("redis unavailable")


@pytest.fixture
def policy() -> ProbeCachePolicy:
    return ProbeCachePolicy(
        success_ttl=30.0,
        failure_ttl=15.0,
        stale_ttl=120.0,
        wait_timeout=0.01,
        poll_interval=0.001,
    )


def test_l1_hot_ttl_uses_success_ttl() -> None:
    policy = ProbeCachePolicy(
        success_ttl=0.25,
        failure_ttl=30.0,
        stale_ttl=120.0,
    )

    assert cache._l1_hot_ttl({"current": {"success": True}}, policy) == 0.25


def test_l1_hot_ttl_uses_failure_ttl() -> None:
    policy = ProbeCachePolicy(
        success_ttl=30.0,
        failure_ttl=0.5,
        stale_ttl=120.0,
    )

    assert cache._l1_hot_ttl({"current": {"success": False}}, policy) == 0.5


def test_l1_hot_ttl_caps_long_ttl_at_local_window() -> None:
    policy = ProbeCachePolicy(
        success_ttl=30.0,
        failure_ttl=15.0,
        stale_ttl=120.0,
    )

    assert (
        cache._l1_hot_ttl({"current": {"success": True}}, policy)
        == cache._L1_HOT_TTL_SEC
    )


@pytest.mark.asyncio
async def test_second_replica_reuses_redis_l2(policy) -> None:
    redis = FakeRedis()
    key = "test:l2"
    await cache.reset_probe_cache(key, redis_client=redis)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {"reachable": True, "source": "origin"}

    first = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )
    await cache.reset_probe_cache()
    second = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )

    assert calls == 1
    assert first.metadata["cache_layer"] == "origin"
    assert second.metadata["cache_layer"] == "redis"
    assert second.metadata["cached"] is True
    assert second.value == first.value
    await cache.reset_probe_cache(key, redis_client=redis)


@pytest.mark.asyncio
async def test_distributed_lock_serves_stale_instead_of_duplicate_origin(policy) -> None:
    redis = FakeRedis()
    key = "test:single-flight"
    await cache.reset_probe_cache(key, redis_client=redis)

    async def healthy_loader():
        return {"reachable": True, "generation": 1}

    await cache.get_or_refresh_probe(
        key,
        healthy_loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )
    await cache.reset_probe_cache()

    redis_key = f"{cache._KEY_PREFIX}{key}"
    envelope = json.loads(redis.values[redis_key])
    envelope["current"]["fetched_at"] = 0.0
    redis.values[redis_key] = json.dumps(envelope)
    redis.values[f"{cache._LOCK_PREFIX}{key}"] = "peer-token"
    calls = 0

    async def duplicate_loader():
        nonlocal calls
        calls += 1
        return {"reachable": True, "generation": 2}

    result = await cache.get_or_refresh_probe(
        key,
        duplicate_loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )

    assert calls == 0
    assert result.value["generation"] == 1
    assert result.metadata["stale"] is True
    assert result.metadata["refresh_in_progress"] is True
    await cache.reset_probe_cache(key, redis_client=redis)


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_direct_probe(policy) -> None:
    redis = FailingRedis()
    key = "test:fallback"
    await cache.reset_probe_cache()
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {"reachable": True}

    result = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )

    assert calls == 1
    assert result.value["reachable"] is True
    assert result.metadata["cache_layer"] == "local_fallback"
    assert result.metadata["redis_available"] is False
    await cache.reset_probe_cache()
