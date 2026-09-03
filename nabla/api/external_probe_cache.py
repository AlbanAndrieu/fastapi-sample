"""Best-effort L1 + Redis L2 cache for sanitized external health probes.

Redis is optional: failures fall back to process-local state and bounded origin
probes. Only JSON-serializable sanitized health data belongs in this cache.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import secrets
import time
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis

from nabla.api.external_probe_cache_redis import (
    KEY_PREFIX as _KEY_PREFIX,
    LOCK_PREFIX as _LOCK_PREFIX,
    SCHEMA_VERSION as _SCHEMA_VERSION,
    acquire_lock as _acquire_lock,
    read_envelope as _redis_get,
    release_lock as _release_lock,
    resolve_redis_client as _redis_client,
    write_envelope as _redis_put,
)
from nabla.api.external_probe_cache_types import ProbeCachePolicy, ProbeCacheResult
from nabla.api.provider_circuit import (
    before_provider_probe,
    record_provider_probe_outcome,
    release_provider_probe,
    reset_provider_circuit_for_probe_key,
    reset_provider_circuits,
)
from nabla.utils.logger import logger

_L1_HOT_TTL_SEC = 5.0
_l1_lock = asyncio.Lock()
_l1: dict[str, tuple[dict[str, Any], float]] = {}
_refresh_locks: dict[str, asyncio.Lock] = {}


def _record(
    value: dict[str, Any],
    *,
    success: bool,
    fetched_at: float,
) -> dict[str, Any]:
    return {"value": deepcopy(value), "success": success, "fetched_at": fetched_at}


def _valid_last_good(
    envelope: dict[str, Any],
    now: float,
    stale_ttl: float,
) -> dict[str, Any] | None:
    candidate = envelope.get("last_good")
    if not isinstance(candidate, dict) or not isinstance(candidate.get("value"), dict):
        return None
    fetched_at = candidate.get("fetched_at")
    if not isinstance(fetched_at, int | float):
        return None
    return candidate if now - float(fetched_at) <= stale_ttl else None


def _current_fresh(
    envelope: dict[str, Any],
    now: float,
    policy: ProbeCachePolicy,
) -> bool:
    current = envelope.get("current")
    if not isinstance(current, dict) or not isinstance(current.get("value"), dict):
        return False
    fetched_at = current.get("fetched_at")
    if not isinstance(fetched_at, int | float):
        return False
    ttl = policy.success_ttl if current.get("success") is True else policy.failure_ttl
    return now - float(fetched_at) < ttl


def _failed_with_last_good(
    envelope: dict[str, Any],
    policy: ProbeCachePolicy,
) -> bool:
    """Return whether current evidence failed while valid prior evidence remains."""
    current = envelope.get("current")
    return (
        isinstance(current, dict)
        and current.get("success") is False
        and _valid_last_good(envelope, time.time(), policy.stale_ttl) is not None
    )


def _metadata(
    envelope: dict[str, Any],
    *,
    layer: str,
    cached: bool,
    stale: bool = False,
    refresh_in_progress: bool = False,
    redis_available: bool = True,
) -> dict[str, Any]:
    current = envelope.get("current")
    current = current if isinstance(current, dict) else {}
    fetched_at = current.get("fetched_at")
    age = (
        max(0.0, time.time() - float(fetched_at))
        if isinstance(fetched_at, int | float)
        else None
    )
    metadata: dict[str, Any] = {
        "cache_layer": layer,
        "cached": cached,
        "stale": stale,
        "refresh_in_progress": refresh_in_progress,
        "redis_available": redis_available,
        "cache_age_seconds": round(age, 3) if age is not None else None,
    }
    circuit = envelope.get("circuit_breaker")
    if isinstance(circuit, dict):
        metadata["circuit_breaker"] = deepcopy(circuit)
    return metadata


def _result_from_envelope(
    envelope: dict[str, Any],
    *,
    layer: str,
    cached: bool,
    policy: ProbeCachePolicy,
    stale: bool = False,
    serve_last_good: bool = False,
    refresh_in_progress: bool = False,
    redis_available: bool = True,
) -> ProbeCacheResult | None:
    current = envelope.get("current")
    last_good_record = _valid_last_good(envelope, time.time(), policy.stale_ttl)
    last_good = (
        deepcopy(last_good_record["value"])
        if last_good_record is not None
        else None
    )
    if serve_last_good and last_good is not None:
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


def _l1_hot_ttl(envelope: dict[str, Any], policy: ProbeCachePolicy) -> float:
    """Cap the local bypass window by the TTL for the cached outcome."""
    current = envelope.get("current")
    success = isinstance(current, dict) and current.get("success") is True
    configured_ttl = policy.success_ttl if success else policy.failure_ttl
    return min(_L1_HOT_TTL_SEC, max(0.0, configured_ttl))


async def _l1_get(
    key: str,
    policy: ProbeCachePolicy,
) -> tuple[dict[str, Any] | None, bool]:
    """Return retained L1 envelope and whether it may bypass a Redis read."""
    async with _l1_lock:
        entry = _l1.get(key)
        if entry is None:
            return None, False
        envelope, stored_at = entry
        age = time.monotonic() - stored_at
        retention = max(policy.success_ttl, policy.failure_ttl, policy.stale_ttl)
        if age >= retention:
            _l1.pop(key, None)
            return None, False
        return deepcopy(envelope), age < _l1_hot_ttl(envelope, policy)


async def _l1_put(key: str, envelope: dict[str, Any]) -> None:
    async with _l1_lock:
        _l1[key] = (deepcopy(envelope), time.monotonic())


async def _get_refresh_lock(key: str) -> asyncio.Lock:
    """Return the process-local single-flight lock for one probe key."""
    async with _l1_lock:
        lock = _refresh_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _refresh_locks[key] = lock
        return lock


async def _wait_for_peer(
    client: Redis,
    key: str,
    policy: ProbeCachePolicy,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + policy.wait_timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(policy.poll_interval)
        envelope = await _redis_get(client, key)
        if envelope is not None and _current_fresh(envelope, time.time(), policy):
            return envelope
    return None


def _cached_result(
    envelope: dict[str, Any] | None,
    *,
    policy: ProbeCachePolicy,
    layer: str,
    redis_available: bool,
) -> ProbeCacheResult | None:
    if envelope is None or not _current_fresh(envelope, time.time(), policy):
        return None
    return _result_from_envelope(
        envelope,
        layer=layer,
        cached=True,
        policy=policy,
        stale=_failed_with_last_good(envelope, policy),
        redis_available=redis_available,
    )


async def get_or_refresh_probe(
    key: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
    *,
    is_success: Callable[[dict[str, Any]], bool],
    policy: ProbeCachePolicy,
    redis_client: Redis | None = None,
) -> ProbeCacheResult:
    """Return a probe using caches, single-flight and provider circuit breakers."""
    envelope, l1_hot = await _l1_get(key, policy)
    if l1_hot:
        result = _cached_result(
            envelope,
            policy=policy,
            layer="l1",
            redis_available=True,
        )
        if result is not None:
            return result

    refresh_lock = await _get_refresh_lock(key)
    async with refresh_lock:
        # A same-process caller may have refreshed while this coroutine waited.
        envelope, l1_hot = await _l1_get(key, policy)
        if l1_hot:
            result = _cached_result(
                envelope,
                policy=policy,
                layer="l1",
                redis_available=True,
            )
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
                    result = _cached_result(
                        remote,
                        policy=policy,
                        layer="redis",
                        redis_available=True,
                    )
                    if result is not None:
                        return result
            except Exception as exc:
                redis_available = False
                logger.debug(
                    "external_probe_cache_redis_read_failed",
                    key=key,
                    exception_type=type(exc).__name__,
                )
        else:
            redis_available = False

        if not redis_available:
            result = _cached_result(
                envelope,
                policy=policy,
                layer="local_fallback",
                redis_available=False,
            )
            if result is not None:
                return result

        last_envelope = envelope or {"schema": _SCHEMA_VERSION}
        lock_token = secrets.token_hex(12)
        lock_acquired = False
        if client is not None and redis_available:
            try:
                lock_acquired = await _acquire_lock(
                    client,
                    key,
                    lock_token,
                    policy.lock_ttl,
                )
                if not lock_acquired:
                    peer = await _wait_for_peer(client, key, policy)
                    if peer is not None:
                        await _l1_put(key, peer)
                        result = _cached_result(
                            peer,
                            layer="redis",
                            policy=policy,
                            redis_available=True,
                        )
                        if result is not None:
                            return result
                    stale = _result_from_envelope(
                        last_envelope,
                        layer="redis",
                        cached=True,
                        stale=True,
                        serve_last_good=True,
                        refresh_in_progress=True,
                        policy=policy,
                    )
                    if stale is not None:
                        return stale
            except Exception as exc:
                redis_available = False
                logger.debug(
                    "external_probe_cache_lock_failed",
                    key=key,
                    exception_type=type(exc).__name__,
                )

        circuit_decision = await before_provider_probe(
            key,
            redis_client=client,
        )
        if not circuit_decision.allowed:
            suppressed = _result_from_envelope(
                last_envelope,
                layer="redis" if redis_available else "local_fallback",
                cached=True,
                stale=_failed_with_last_good(last_envelope, policy),
                serve_last_good=_failed_with_last_good(last_envelope, policy),
                policy=policy,
                redis_available=redis_available,
            )
            if suppressed is not None:
                suppressed.metadata["circuit_breaker"] = circuit_decision.metadata(
                    origin_suppressed=True
                )
                return suppressed

        try:
            try:
                value = await loader()
            except Exception:
                await record_provider_probe_outcome(
                    circuit_decision,
                    success=False,
                )
                raise
            success = bool(is_success(value))
            circuit_metadata = await record_provider_probe_outcome(
                circuit_decision,
                success=success,
            )
            fetched_at = time.time()
            previous_good = _valid_last_good(
                last_envelope,
                fetched_at,
                policy.stale_ttl,
            )
            current = _record(value, success=success, fetched_at=fetched_at)
            new_envelope: dict[str, Any] = {
                "schema": _SCHEMA_VERSION,
                "current": current,
                "last_good": deepcopy(current) if success else previous_good,
            }
            if circuit_metadata:
                new_envelope["circuit_breaker"] = circuit_metadata
            await _l1_put(key, new_envelope)
            if client is not None and redis_available:
                try:
                    await _redis_put(client, key, new_envelope, policy)
                except Exception as exc:
                    redis_available = False
                    logger.debug(
                        "external_probe_cache_redis_write_failed",
                        key=key,
                        exception_type=type(exc).__name__,
                    )
            result = _result_from_envelope(
                new_envelope,
                layer="origin" if redis_available else "local_fallback",
                cached=False,
                policy=policy,
                stale=not success and previous_good is not None,
                redis_available=redis_available,
            )
            if result is None:  # pragma: no cover - loader contract protects this branch.
                raise RuntimeError("external probe cache produced no result")
            return result
        finally:
            await release_provider_probe(circuit_decision)
            if client is not None and lock_acquired:
                await _release_lock(client, key, lock_token)


async def reset_probe_cache(
    key: str | None = None,
    *,
    redis_client: Redis | None = None,
) -> None:
    """Reset local state and optional Redis entries for deterministic tests."""
    async with _l1_lock:
        if key is None:
            _l1.clear()
            _refresh_locks.clear()
        else:
            _l1.pop(key, None)
            _refresh_locks.pop(key, None)
    if key is None:
        await reset_provider_circuits()
    else:
        await reset_provider_circuit_for_probe_key(
            key,
            redis_client=redis_client,
        )
    if redis_client is not None and key is not None:
        await redis_client.delete(
            f"{_KEY_PREFIX}{key}",
            f"{_LOCK_PREFIX}{key}",
        )
