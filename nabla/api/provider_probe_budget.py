"""Best-effort per-provider rate budgets for external origin probes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from redis.asyncio import Redis

from nabla.api.external_probe_cache_redis import resolve_redis_client
from nabla.utils.logger import logger

_RATE_PREFIX = "health:v1:rate:"


@dataclass(frozen=True, slots=True)
class ProviderProbeRatePolicy:
    """Maximum admitted origin attempts for one provider in a fixed window."""

    max_requests: int
    window_seconds: int = 60

    def __post_init__(self) -> None:
        if self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.window_seconds < 1:
            raise ValueError("window_seconds must be at least 1 second")


@dataclass(frozen=True, slots=True)
class ProviderProbeBudgetDecision:
    """Admission result safe to expose as bounded diagnostic metadata."""

    provider: str | None
    allowed: bool
    count: int = 0
    max_requests: int = 0
    window_seconds: int = 0
    redis_shared: bool = False

    def metadata(self, *, origin_suppressed: bool) -> dict[str, object]:
        if self.provider is None or self.max_requests <= 0:
            return {}
        return {
            "provider": self.provider,
            "allowed": self.allowed,
            "count": self.count,
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "remaining": max(0, self.max_requests - self.count),
            "redis_shared": self.redis_shared,
            "origin_suppressed": origin_suppressed,
        }


# Two complete cold-start passes per minute for the currently declared keys:
# TrueNAS: api; pfSense: liveness/posture/snort2c; Cloudflare: tunnels/exposure.
_PROVIDER_RATE_POLICIES: dict[str, ProviderProbeRatePolicy] = {
    "truenas": ProviderProbeRatePolicy(max_requests=2),
    "pfsense": ProviderProbeRatePolicy(max_requests=6),
    "cloudflare": ProviderProbeRatePolicy(max_requests=4),
}
_local_lock = asyncio.Lock()
_local_counts: dict[tuple[str, int], int] = {}


def _now() -> float:
    return time.time()


def _provider_for_probe_key(key: str) -> str | None:
    provider = key.partition(":")[0].strip().lower()
    return provider if provider in _PROVIDER_RATE_POLICIES else None


def _bucket_id(policy: ProviderProbeRatePolicy) -> int:
    return int(_now() // policy.window_seconds)


async def _local_count(
    provider: str,
    policy: ProviderProbeRatePolicy,
    bucket: int,
) -> int:
    async with _local_lock:
        for key in tuple(_local_counts):
            if key[0] == provider and key[1] != bucket:
                _local_counts.pop(key, None)
        counter_key = (provider, bucket)
        count = _local_counts.get(counter_key, 0) + 1
        _local_counts[counter_key] = count
        return count


async def _remote_count(
    client: Redis,
    provider: str,
    policy: ProviderProbeRatePolicy,
    bucket: int,
) -> int:
    key = f"{_RATE_PREFIX}{provider}:{bucket}"
    async with client.pipeline(transaction=True) as pipeline:
        pipeline.incr(key)
        pipeline.expire(key, policy.window_seconds + 5)
        result = await pipeline.execute()
    return int(result[0])


async def admit_provider_probe(
    probe_key: str,
    *,
    redis_client: Redis | None = None,
    redis_available: bool = True,
) -> ProviderProbeBudgetDecision:
    """Admit one origin attempt using Redis when available and local state otherwise."""
    provider = _provider_for_probe_key(probe_key)
    if provider is None:
        return ProviderProbeBudgetDecision(provider=None, allowed=True)

    policy = _PROVIDER_RATE_POLICIES[provider]
    bucket = _bucket_id(policy)
    local_count = await _local_count(provider, policy, bucket)
    local_allowed = local_count <= policy.max_requests

    client = redis_client
    if client is None and redis_available:
        client = resolve_redis_client()
    if client is None or not redis_available:
        return ProviderProbeBudgetDecision(
            provider=provider,
            allowed=local_allowed,
            count=local_count,
            max_requests=policy.max_requests,
            window_seconds=policy.window_seconds,
            redis_shared=False,
        )

    try:
        remote_count = await _remote_count(client, provider, policy, bucket)
    except Exception as exc:
        logger.debug(
            "provider_probe_budget_redis_failed",
            provider=provider,
            exception_type=type(exc).__name__,
        )
        return ProviderProbeBudgetDecision(
            provider=provider,
            allowed=local_allowed,
            count=local_count,
            max_requests=policy.max_requests,
            window_seconds=policy.window_seconds,
            redis_shared=False,
        )

    count = max(local_count, remote_count)
    return ProviderProbeBudgetDecision(
        provider=provider,
        allowed=local_allowed and remote_count <= policy.max_requests,
        count=count,
        max_requests=policy.max_requests,
        window_seconds=policy.window_seconds,
        redis_shared=True,
    )


async def reset_provider_probe_budgets(provider: str | None = None) -> None:
    """Reset process-local counters for deterministic tests and local maintenance."""
    async with _local_lock:
        if provider is None:
            _local_counts.clear()
            return
        for key in tuple(_local_counts):
            if key[0] == provider:
                _local_counts.pop(key, None)


async def reset_provider_probe_budget_for_probe_key(probe_key: str) -> None:
    """Reset the local provider counter associated with one probe key."""
    provider = _provider_for_probe_key(probe_key)
    if provider is not None:
        await reset_provider_probe_budgets(provider)
