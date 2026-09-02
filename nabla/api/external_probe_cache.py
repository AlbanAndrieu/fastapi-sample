"""Best-effort L1 + Redis L2 cache for sanitized external health probes.

The cache is deliberately optional: Redis failures fall back to process-local
state and direct bounded probes. Only JSON-serializable sanitized health data is
stored; credentials and raw provider responses must never be passed here.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import json
import secrets
import time
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis

from nabla.utils.logger import logger

_SCHEMA_VERSION = 1
_KEY_PREFIX = "health:v1:probe:"
_LOCK_PREFIX = "health:v1:lock:"
_L1_MAX_TTL_SEC = 5.0
_l1_lock = asyncio.Lock()
_l1: dict[str, tuple[dict[str, Any], float]] = {}


@dataclass(frozen=True, slots=True)
class ProbeCachePolicy:
    """Fresh/failure/stale windows for one external probe."""

    success_ttl: float
    failure_ttl: float
    stale_ttl: float
    lock_ttl: int = 15
    wait_timeout: float = 0.6
    poll_interval: float = 0.1


@dataclass(frozen=True, slots=True)
class ProbeCacheResult:
    """Current cached/origin value plus optional last-known-good evidence."""

    value: dict[str, Any]
    metadata: dict[str, Any]
    last_good: dict[str, Any] | None = None


def _redis_client() -> Redis | None:
    """Resolve the existing application Redis client lazily to avoid import cycles."""
    try:
        from nabla.api.demo.socket.redis import redis as client
    except (ImportError, RuntimeError):  # pragma: no cover - defensive startup fallback.
        return None
    return client


def _record(value: dict[str, Any], *, success: bool, fetched_at: float) -> dict[str, Any]:
    return {
        "value": deepcopy(value),
        "success": success,
        "fetched_at": fetched_at,
    }


def _valid_last_good(envelope: dict[str, Any], now: float, stale_ttl: float) -> dict[str, Any] | None:
    candidate = envelope.get("last_good")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("value"), dict):
        return None
    fetched_at = candidate.get("fetched_at")
    if not isinstance(fetched_at, int | float) or now - float(fetched_at) > stale_ttl:
        return None
    return candidate


def _current_fresh(envelope: dict[str, Any], now: float, policy: ProbeCachePolicy) -> bool:
    current = envelope.get("current")
    if not isinstance(current, dict) or not isinstance(current.get("value"), dict):
        return False
    fetched_at = current.get("fetched_at")
    if not isinstance(fetched_at, int | float):
        return False
    ttl = policy.success_ttl if current.get("success") is True else policy.failure_ttl
    return now - float(fetched_at) < ttl


def _metadata(
    envelope: dict[str, Any],
    *,
    layer: str,
    cached: bool,
    stale: bool = False,
    refresh_in_progress: bool = False,
    redis_available: bool = True,
) -> dict[str, Any]:
    current = envelope.get("current") if isinstance(envelope.get("current"), dict) else {}
    fetched_at = current.get("fetched_at")
    age = max(0.0, time.time() - float(fetched_at)) if isinstance(fetched_at, int | float) else None
    return {
        "cache_layer": layer,
        "cached": cached,
        "stale": stale,
        "refresh_in_progress": refresh_in_progress,
        "redis_available": redis_available,
        "cache_age_seconds": round(age, 3) if age is not None else None,
    }


def _result_from_envelope(
    envelope: dict[str, Any],
    *,
    layer: str,
    cached: bool,
    policy: ProbeCachePolicy,
    stale: bool = False,
    refresh_in_progress: bool = False,
    redis_available: bool = True,
) -> ProbeCacheResult | None:
    now = time.time()
    current = envelope.get("current")
    last_good_record = _valid_last_good(envelope, now, policy.stale_ttl)
    last_good = deepcopy(last_good_record["value"]) if last_good_record is not None else None

    if stale and last_good is not None:
        value = deepcopy(last_good)
    elif isinstance(current, dict) and isinstance(current.get("value"), dict):
        value = deepcopy(current["value"])
    else:
        return None

    return ProbeCacheResult(
        value=value,
        metadata=_metadata(
            envelope,
            layer=layer,
            cached=cached,
            stale=stale,
            refresh_in_progress=refresh_in_progress,
            redis_available=redis_available,
        ),
        last_good=last_good,
    )


async def _l1_get(key: str, policy: ProbeCachePolicy) -> dict[str, Any] | None:
    async with _l1_lock:
        entry = _l1.get(key)
        if entry is None:
            return None
        envelope, stored_at = entry
        if time.monotonic() - stored_at >= min(_L1_MAX_TTL_SEC, policy.success_ttl, policy.failure_ttl):
            _l1.pop(key, None)
            return None
        return deepcopy(envelope)


async def _l1_put(key: str, envelope: dict[str, Any]) -> None:
    async with _l1_lock:
        _l1[key] = (deepcopy(envelope), time.monotonic())


async def _redis_get(client: Redis, key: str) -> dict[str, Any] | None:
    raw = await client.get(f"{_KEY_PREFIX}{key}")
    if not isinstance(raw, str):
        return None
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict) or envelope.get("schema") != _SCHEMA_VERSION:
        return None
    return envelope


async def _redis_put(client: Redis, key: str, envelope: dict[str, Any], policy: ProbeCachePolicy) -> None:
    ttl = max(policy.success_ttl, policy.failure_ttl, policy.stale_ttl)
    await client.set(
        f"{_KEY_PREFIX}{key}",
        json.dumps(envelope, separators=(",", ":"), sort_keys=True),
        ex=max(1, int(ttl)),
    )


async def _acquire_lock(client: Redis, key: str, token: str, ttl: int) -> bool:
    return bool(await client.set(f"{_LOCK_PREFIX}{key}", token, nx=True, ex=max(1, ttl)))


async def _release_lock(client: Redis, key: str, token: str) -> None:
    script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    try:
        await client.eval(script, 1, f"{_LOCK_PREFIX}{key}", token)
    except Exception:  # pragma: no cover - lock expiry is the safety net.
        pass


async def _wait_for_peer(client: Redis, key: str, policy: ProbeCachePolicy) -> dict[str, Any] | None:
    deadline = time.monotonic() + policy.wait_timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(policy.poll_interval)
        envelope = await _redis_get(client, key)
        if envelope is not None and _current_fresh(envelope, time.time(), policy):
            return envelope
    return None


async def get_or_refresh_probe(
    key: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
    *,
    is_success: Callable[[dict[str, Any]], bool],
    policy: ProbeCachePolicy,
    redis_client: Redis | None = None,
) -> ProbeCacheResult:
    """Return a probe using L1, Redis L2 and distributed single-flight refresh."""
    now = time.time()
    envelope = await _l1_get(key, policy)
    if envelope is not None and _current_fresh(envelope, now, policy):
        result = _result_from_envelope(envelope, layer="l1", cached=True, policy=policy)
        if result is not None:
            return result

    client = redis_client if redis_client is not None else _redis_client()
    redis_available = client is not None
    if client is not None:
        try:
            remote = await _redis_get(client, key)
            if remote is not None:
                envelope = remote
                await _l1_put(key, remote)
                if _current_fresh(remote, time.time(), policy):
                    result = _result_from_envelope(remote, layer="redis", cached=True, policy=policy)
                    if result is not None:
                        return result
        except Exception as exc:  # Redis must never make the external probe unavailable.
            redis_available = False
            logger.debug("external_probe_cache_redis_read_failed", key=key, exception_type=type(exc).__name__)

    last_envelope = envelope if isinstance(envelope, dict) else {"schema": _SCHEMA_VERSION}
    lock_token = secrets.token_hex(12)
    lock_acquired = False
    if client is not None and redis_available:
        try:
            lock_acquired = await _acquire_lock(client, key, lock_token, policy.lock_ttl)
            if not lock_acquired:
                peer = await _wait_for_peer(client, key, policy)
                if peer is not None:
                    await _l1_put(key, peer)
                    result = _result_from_envelope(peer, layer="redis", cached=True, policy=policy)
                    if result is not None:
                        return result
                stale = _result_from_envelope(
                    last_envelope,
                    layer="redis",
                    cached=True,
                    stale=True,
                    refresh_in_progress=True,
                    policy=policy,
                )
                if stale is not None:
                    return stale
        except Exception as exc:
            redis_available = False
            logger.debug("external_probe_cache_lock_failed", key=key, exception_type=type(exc).__name__)

    try:
        value = await loader()
        success = bool(is_success(value))
        fetched_at = time.time()
        previous_good = _valid_last_good(last_envelope, fetched_at, policy.stale_ttl)
        current = _record(value, success=success, fetched_at=fetched_at)
        new_envelope: dict[str, Any] = {
            "schema": _SCHEMA_VERSION,
            "current": current,
            "last_good": current if success else previous_good,
        }
        await _l1_put(key, new_envelope)
        if client is not None and redis_available:
            try:
                await _redis_put(client, key, new_envelope, policy)
            except Exception as exc:
                redis_available = False
                logger.debug("external_probe_cache_redis_write_failed", key=key, exception_type=type(exc).__name__)
        result = _result_from_envelope(
            new_envelope,
            layer="origin" if redis_available else "local_fallback",
            cached=False,
            policy=policy,
            redis_available=redis_available,
        )
        if result is None:  # pragma: no cover - loader contract protects this branch.
            raise RuntimeError("external probe cache produced no result")
        return result
    finally:
        if client is not None and lock_acquired:
            await _release_lock(client, key, lock_token)


async def reset_probe_cache(key: str | None = None, *, redis_client: Redis | None = None) -> None:
    """Reset process-local state and optionally matching Redis entries for tests/maintenance."""
    async with _l1_lock:
        if key is None:
            _l1.clear()
        else:
            _l1.pop(key, None)
    client = redis_client
    if client is not None and key is not None:
        await client.delete(f"{_KEY_PREFIX}{key}", f"{_LOCK_PREFIX}{key}")
