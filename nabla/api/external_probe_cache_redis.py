"""Redis L2 storage and distributed-lock primitives for external probe caching."""

from __future__ import annotations

import json
import os
from typing import Any

from redis.asyncio import Redis

from nabla.api.external_probe_cache_types import ProbeCachePolicy
from nabla.utils.logger import logger

SCHEMA_VERSION = 1
KEY_PREFIX = "health:v1:probe:"
LOCK_PREFIX = "health:v1:lock:"


def resolve_redis_client() -> Redis | None:
    """Resolve the shared client only when REDIS_URL is explicitly configured."""
    if not os.getenv("REDIS_URL", "").strip():
        return None
    try:
        from nabla.api.demo.socket.redis import redis as client
    except (ImportError, RuntimeError):  # pragma: no cover - startup fallback.
        return None
    return client


async def read_envelope(client: Redis, key: str) -> dict[str, Any] | None:
    """Read and validate one versioned cache envelope."""
    raw = await client.get(f"{KEY_PREFIX}{key}")
    if not isinstance(raw, str):
        return None
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict) or envelope.get("schema") != SCHEMA_VERSION:
        return None
    return envelope


async def write_envelope(
    client: Redis,
    key: str,
    envelope: dict[str, Any],
    policy: ProbeCachePolicy,
) -> None:
    """Persist a sanitized cache envelope for the longest evidence window."""
    ttl = max(policy.success_ttl, policy.failure_ttl, policy.stale_ttl)
    await client.set(
        f"{KEY_PREFIX}{key}",
        json.dumps(envelope, separators=(",", ":"), sort_keys=True),
        ex=max(1, int(ttl)),
    )


async def acquire_lock(client: Redis, key: str, token: str, ttl: int) -> bool:
    """Acquire the per-probe single-flight lock."""
    return bool(
        await client.set(
            f"{LOCK_PREFIX}{key}",
            token,
            nx=True,
            ex=max(1, ttl),
        )
    )


async def release_lock(client: Redis, key: str, token: str) -> None:
    """Release a lock only when its ownership token still matches."""
    script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    try:
        await client.eval(script, 1, f"{LOCK_PREFIX}{key}", token)
    except Exception as exc:  # pragma: no cover - lock expiry is the safety net.
        logger.debug(
            "external_probe_cache_lock_release_failed",
            key=key,
            exception_type=type(exc).__name__,
        )
