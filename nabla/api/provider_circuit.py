"""Best-effort provider-level circuit breakers for external health probes.

Circuit state is process-local first and optionally mirrored to Redis so replicas
share coarse pressure-relief state. Redis failures never block origin probing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import secrets
import time
from typing import Any

from redis.asyncio import Redis

from nabla.api.external_probe_cache_redis import (
    LOCK_PREFIX,
    acquire_lock,
    release_lock,
    resolve_redis_client,
)
from nabla.utils.logger import logger

_CIRCUIT_SCHEMA = 1
_CIRCUIT_PREFIX = "health:v1:circuit:"


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    """Failure threshold and bounded backoff for one external provider."""

    failure_threshold: int
    base_backoff: float
    max_backoff: float
    jitter_ratio: float = 0.1
    half_open_lock_ttl: int = 20

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        for field_name in ("base_backoff", "max_backoff"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be a finite positive value")
        if self.max_backoff < self.base_backoff:
            raise ValueError("max_backoff must be greater than or equal to base_backoff")
        if not math.isfinite(self.jitter_ratio) or not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if self.half_open_lock_ttl < 1:
            raise ValueError("half_open_lock_ttl must be at least 1 second")

    def backoff_seconds(self, failures: int) -> float:
        """Return capped exponential backoff with positive jitter."""
        exponent = max(0, failures - self.failure_threshold)
        base = min(self.max_backoff, self.base_backoff * (2**exponent))
        if self.jitter_ratio == 0 or base >= self.max_backoff:
            return base
        fraction = secrets.randbelow(10_001) / 10_000
        return min(self.max_backoff, base * (1 + self.jitter_ratio * fraction))


@dataclass(frozen=True, slots=True)
class ProviderCircuitState:
    """Coarse state safe to persist in Redis."""

    failures: int = 0
    open_until: float = 0.0


@dataclass(slots=True)
class CircuitDecision:
    """One origin-probe permission decision and optional half-open ownership."""

    provider: str | None
    policy: CircuitBreakerPolicy | None
    state: ProviderCircuitState
    allowed: bool = True
    half_open: bool = False
    redis_available: bool = False
    client: Redis | None = None
    lock_token: str | None = None

    def metadata(self, *, origin_suppressed: bool = False) -> dict[str, Any]:
        if self.provider is None or self.policy is None:
            return {}
        now = _now()
        if self.state.open_until > now:
            state_name = "open"
        elif self.state.failures >= self.policy.failure_threshold:
            state_name = "half_open"
        else:
            state_name = "closed"
        retry_after = max(0, math.ceil(self.state.open_until - now))
        return {
            "provider": self.provider,
            "state": state_name,
            "failures": self.state.failures,
            "retry_after_seconds": retry_after,
            "origin_suppressed": origin_suppressed,
            "redis_shared": self.redis_available,
        }


_PROVIDER_POLICIES: dict[str, CircuitBreakerPolicy] = {
    "truenas": CircuitBreakerPolicy(
        failure_threshold=2,
        base_backoff=180.0,
        max_backoff=900.0,
        jitter_ratio=0.1,
    ),
    "pfsense": CircuitBreakerPolicy(
        failure_threshold=3,
        base_backoff=180.0,
        max_backoff=900.0,
        jitter_ratio=0.1,
    ),
    "cloudflare": CircuitBreakerPolicy(
        failure_threshold=3,
        base_backoff=90.0,
        max_backoff=600.0,
        jitter_ratio=0.15,
    ),
}
_state_lock = asyncio.Lock()
_local_states: dict[str, ProviderCircuitState] = {}
_half_open_in_progress: set[str] = set()


def _now() -> float:
    return time.time()


def _provider_for_probe_key(key: str) -> str | None:
    provider = key.partition(":")[0].strip().lower()
    return provider if provider in _PROVIDER_POLICIES else None


def _decode_state(raw: object) -> ProviderCircuitState | None:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != _CIRCUIT_SCHEMA:
        return None
    failures = payload.get("failures")
    open_until = payload.get("open_until")
    if not isinstance(failures, int) or failures < 0:
        return None
    if not isinstance(open_until, int | float) or not math.isfinite(float(open_until)):
        return None
    return ProviderCircuitState(failures=failures, open_until=max(0.0, float(open_until)))


def _merge_states(
    local: ProviderCircuitState,
    remote: ProviderCircuitState | None,
) -> ProviderCircuitState:
    if remote is None:
        return local
    return ProviderCircuitState(
        failures=max(local.failures, remote.failures),
        open_until=max(local.open_until, remote.open_until),
    )


async def _read_remote_state(client: Redis, provider: str) -> ProviderCircuitState | None:
    return _decode_state(await client.get(f"{_CIRCUIT_PREFIX}{provider}"))


async def _write_remote_state(
    client: Redis,
    provider: str,
    state: ProviderCircuitState,
    policy: CircuitBreakerPolicy,
) -> None:
    payload = json.dumps(
        {
            "schema": _CIRCUIT_SCHEMA,
            "failures": state.failures,
            "open_until": state.open_until,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    await client.set(
        f"{_CIRCUIT_PREFIX}{provider}",
        payload,
        ex=max(1, int(policy.max_backoff * 2)),
    )


async def _load_state(
    provider: str,
    client: Redis | None,
) -> tuple[ProviderCircuitState, bool]:
    async with _state_lock:
        local = _local_states.get(provider, ProviderCircuitState())
    if client is None:
        return local, False
    try:
        remote = await _read_remote_state(client, provider)
    except Exception as exc:
        logger.debug(
            "provider_circuit_redis_read_failed",
            provider=provider,
            exception_type=type(exc).__name__,
        )
        return local, False
    merged = _merge_states(local, remote)
    async with _state_lock:
        _local_states[provider] = merged
    return merged, True


async def before_provider_probe(
    probe_key: str,
    *,
    redis_client: Redis | None = None,
) -> CircuitDecision:
    """Return whether an origin probe may run for the probe's provider."""
    provider = _provider_for_probe_key(probe_key)
    policy = _PROVIDER_POLICIES.get(provider or "")
    if provider is None or policy is None:
        return CircuitDecision(None, None, ProviderCircuitState())

    client = redis_client if redis_client is not None else resolve_redis_client()
    state, redis_available = await _load_state(provider, client)
    now = _now()
    if state.open_until > now:
        return CircuitDecision(
            provider,
            policy,
            state,
            allowed=False,
            redis_available=redis_available,
            client=client,
        )

    half_open = state.failures >= policy.failure_threshold
    if not half_open:
        return CircuitDecision(
            provider,
            policy,
            state,
            redis_available=redis_available,
            client=client,
        )

    async with _state_lock:
        if provider in _half_open_in_progress:
            return CircuitDecision(
                provider,
                policy,
                state,
                allowed=False,
                half_open=True,
                redis_available=redis_available,
                client=client,
            )
        _half_open_in_progress.add(provider)

    token: str | None = None
    if client is not None and redis_available:
        token = secrets.token_hex(12)
        try:
            acquired = await acquire_lock(
                client,
                f"circuit:{provider}",
                token,
                policy.half_open_lock_ttl,
            )
        except Exception as exc:
            logger.debug(
                "provider_circuit_half_open_lock_failed",
                provider=provider,
                exception_type=type(exc).__name__,
            )
            redis_available = False
            token = None
        else:
            if not acquired:
                async with _state_lock:
                    _half_open_in_progress.discard(provider)
                return CircuitDecision(
                    provider,
                    policy,
                    state,
                    allowed=False,
                    half_open=True,
                    redis_available=True,
                    client=client,
                )

    return CircuitDecision(
        provider,
        policy,
        state,
        allowed=True,
        half_open=True,
        redis_available=redis_available,
        client=client,
        lock_token=token,
    )


async def record_provider_probe_outcome(
    decision: CircuitDecision,
    *,
    success: bool,
) -> dict[str, Any]:
    """Record one origin result and return sanitized breaker metadata."""
    provider = decision.provider
    policy = decision.policy
    if provider is None or policy is None:
        return {}

    state, redis_available = await _load_state(provider, decision.client)
    if success:
        new_state = ProviderCircuitState()
        async with _state_lock:
            _local_states.pop(provider, None)
        if decision.client is not None and redis_available:
            try:
                await decision.client.delete(f"{_CIRCUIT_PREFIX}{provider}")
            except Exception as exc:
                redis_available = False
                logger.debug(
                    "provider_circuit_redis_reset_failed",
                    provider=provider,
                    exception_type=type(exc).__name__,
                )
    else:
        failures = max(state.failures, decision.state.failures) + 1
        open_until = 0.0
        if failures >= policy.failure_threshold:
            open_until = _now() + policy.backoff_seconds(failures)
        new_state = ProviderCircuitState(failures=failures, open_until=open_until)
        async with _state_lock:
            _local_states[provider] = new_state
        if decision.client is not None and redis_available:
            try:
                await _write_remote_state(
                    decision.client,
                    provider,
                    new_state,
                    policy,
                )
            except Exception as exc:
                redis_available = False
                logger.debug(
                    "provider_circuit_redis_write_failed",
                    provider=provider,
                    exception_type=type(exc).__name__,
                )

    final = CircuitDecision(
        provider,
        policy,
        new_state,
        allowed=True,
        half_open=decision.half_open,
        redis_available=redis_available,
        client=decision.client,
        lock_token=decision.lock_token,
    )
    return final.metadata()


async def release_provider_probe(decision: CircuitDecision) -> None:
    """Release local/distributed half-open ownership after an origin probe."""
    provider = decision.provider
    if provider is None or not decision.half_open:
        return
    async with _state_lock:
        _half_open_in_progress.discard(provider)
    if decision.client is not None and decision.lock_token is not None:
        await release_lock(
            decision.client,
            f"circuit:{provider}",
            decision.lock_token,
        )


async def reset_provider_circuit_for_probe_key(
    probe_key: str,
    *,
    redis_client: Redis | None = None,
) -> None:
    """Reset one provider circuit; intended for deterministic tests."""
    provider = _provider_for_probe_key(probe_key)
    if provider is None:
        return
    async with _state_lock:
        _local_states.pop(provider, None)
        _half_open_in_progress.discard(provider)
    if redis_client is not None:
        await redis_client.delete(
            f"{_CIRCUIT_PREFIX}{provider}",
            f"{LOCK_PREFIX}circuit:{provider}",
        )


async def reset_provider_circuits() -> None:
    """Clear process-local circuit state without scanning Redis."""
    async with _state_lock:
        _local_states.clear()
        _half_open_in_progress.clear()
