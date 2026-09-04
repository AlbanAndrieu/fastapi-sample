"""Real Redis integration coverage for external probe cache primitives."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import os
import time

import pytest
from redis.asyncio import Redis

from nabla.api import external_probe_cache as cache
from nabla.api.external_probe_cache_redis import (
    KEY_PREFIX,
    LOCK_PREFIX,
    SCHEMA_VERSION,
    acquire_lock,
    read_envelope,
    release_lock,
    write_envelope,
)
from nabla.api.external_probe_cache_types import ProbeCachePolicy

_REDIS_URL = os.getenv("REDIS_INTEGRATION_URL", "").strip()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _REDIS_URL,
        reason="REDIS_INTEGRATION_URL is required for real Redis integration tests",
    ),
]


@asynccontextmanager
async def _redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(_REDIS_URL, decode_responses=True)
    await client.ping()
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


def _policy() -> ProbeCachePolicy:
    return ProbeCachePolicy(
        success_ttl=0.1,
        failure_ttl=0.1,
        stale_ttl=1.0,
        wait_timeout=0.05,
        poll_interval=0.005,
    )


@pytest.mark.asyncio
async def test_real_redis_envelope_expires() -> None:
    async with _redis_client() as client:
        key = "integration:expiry"
        envelope = {
            "schema": SCHEMA_VERSION,
            "current": {
                "value": {"reachable": True},
                "success": True,
                "fetched_at": time.time(),
            },
            "last_good": None,
        }

        await write_envelope(client, key, envelope, _policy())

        assert await read_envelope(client, key) == envelope
        ttl = await client.ttl(f"{KEY_PREFIX}{key}")
        assert 0 <= ttl <= 1

        await asyncio.sleep(1.2)

        assert await read_envelope(client, key) is None


@pytest.mark.asyncio
async def test_real_redis_rejects_unknown_cache_schema() -> None:
    async with _redis_client() as client:
        key = "integration:schema"
        await client.set(
            f"{KEY_PREFIX}{key}",
            json.dumps({"schema": SCHEMA_VERSION + 1, "current": {}}),
            ex=10,
        )

        assert await read_envelope(client, key) is None


@pytest.mark.asyncio
async def test_real_redis_lock_release_requires_owner_token() -> None:
    async with _redis_client() as client:
        key = "integration:lock"

        assert await acquire_lock(client, key, "owner-token", 10) is True
        assert await acquire_lock(client, key, "other-token", 10) is False

        await release_lock(client, key, "other-token")
        assert await client.get(f"{LOCK_PREFIX}{key}") == "owner-token"

        await release_lock(client, key, "owner-token")
        assert await client.get(f"{LOCK_PREFIX}{key}") is None


@pytest.mark.asyncio
async def test_real_redis_reuses_cached_result_after_local_replica_reset() -> None:
    async with _redis_client() as client:
        key = "integration:cross-replica"
        policy = ProbeCachePolicy(
            success_ttl=30.0,
            failure_ttl=15.0,
            stale_ttl=120.0,
            wait_timeout=0.05,
            poll_interval=0.005,
        )
        await cache.reset_probe_cache(key, redis_client=client)
        calls = 0

        async def loader() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"reachable": True, "source": "origin"}

        first = await cache.get_or_refresh_probe(
            key,
            loader,
            is_success=lambda value: value["reachable"] is True,
            policy=policy,
            redis_client=client,
        )

        await cache.reset_probe_cache()

        second = await cache.get_or_refresh_probe(
            key,
            loader,
            is_success=lambda value: value["reachable"] is True,
            policy=policy,
            redis_client=client,
        )

        assert calls == 1
        assert first.metadata["cache_layer"] == "origin"
        assert second.metadata["cache_layer"] == "redis"
        assert second.metadata["cached"] is True
        assert second.value == first.value

        await cache.reset_probe_cache(key, redis_client=client)
