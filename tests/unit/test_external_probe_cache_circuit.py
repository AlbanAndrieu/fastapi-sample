"""Integration tests between external probe caching and provider circuits."""

import json

import pytest

from nabla.api import external_probe_cache as cache
from nabla.api import provider_circuit as circuit
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
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
            self.values.pop(key, None)
        return deleted


def _expire_cached_failure(redis: FakeRedis, key: str) -> None:
    envelope, stored_at = cache._l1[key]
    envelope["current"]["fetched_at"] = 0.0
    cache._l1[key] = (envelope, stored_at)

    redis_key = f"{cache._KEY_PREFIX}{key}"
    remote = json.loads(redis.values[redis_key])
    remote["current"]["fetched_at"] = 0.0
    redis.values[redis_key] = json.dumps(remote)


@pytest.mark.asyncio
async def test_open_circuit_suppresses_origin_and_releases_cache_lock(monkeypatch) -> None:
    redis = FakeRedis()
    key = "truenas:circuit-integration"
    policy = ProbeCachePolicy(
        success_ttl=30.0,
        failure_ttl=1.0,
        stale_ttl=120.0,
        wait_timeout=0.01,
        poll_interval=0.001,
    )
    breaker_policy = circuit.CircuitBreakerPolicy(
        failure_threshold=2,
        base_backoff=30.0,
        max_backoff=60.0,
        jitter_ratio=0.0,
    )
    monkeypatch.setitem(circuit._PROVIDER_POLICIES, "truenas", breaker_policy)
    await cache.reset_probe_cache(key, redis_client=redis)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {"reachable": False, "generation": calls, "error": "timeout"}

    first = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )
    _expire_cached_failure(redis, key)
    second = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )
    _expire_cached_failure(redis, key)
    third = await cache.get_or_refresh_probe(
        key,
        loader,
        is_success=lambda value: value["reachable"] is True,
        policy=policy,
        redis_client=redis,
    )

    assert calls == 2
    assert first.metadata["circuit_breaker"]["state"] == "closed"
    assert second.metadata["circuit_breaker"]["state"] == "open"
    assert third.value["generation"] == 2
    assert third.metadata["cached"] is True
    assert third.metadata["circuit_breaker"]["state"] == "open"
    assert third.metadata["circuit_breaker"]["origin_suppressed"] is True
    assert f"{cache._LOCK_PREFIX}{key}" not in redis.values
    await cache.reset_probe_cache(key, redis_client=redis)
