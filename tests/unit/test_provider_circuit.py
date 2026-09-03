"""Tests for provider-level external probe circuit breakers."""

import pytest

from nabla.api import provider_circuit as circuit


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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"failure_threshold": 0, "base_backoff": 1.0, "max_backoff": 2.0},
        {"failure_threshold": 1, "base_backoff": 0.0, "max_backoff": 2.0},
        {"failure_threshold": 1, "base_backoff": 2.0, "max_backoff": 1.0},
        {
            "failure_threshold": 1,
            "base_backoff": 1.0,
            "max_backoff": 2.0,
            "jitter_ratio": 1.1,
        },
        {
            "failure_threshold": 1,
            "base_backoff": 1.0,
            "max_backoff": 2.0,
            "half_open_lock_ttl": 0,
        },
    ],
)
def test_circuit_policy_rejects_invalid_budgets(kwargs) -> None:
    with pytest.raises(ValueError):
        circuit.CircuitBreakerPolicy(**kwargs)


@pytest.mark.asyncio
async def test_repeated_failures_open_then_half_open_after_backoff(monkeypatch) -> None:
    await circuit.reset_provider_circuits()
    clock = [1_000.0]
    policy = circuit.CircuitBreakerPolicy(
        failure_threshold=2,
        base_backoff=10.0,
        max_backoff=20.0,
        jitter_ratio=0.0,
    )
    monkeypatch.setitem(circuit._PROVIDER_POLICIES, "truenas", policy)
    monkeypatch.setattr(circuit, "_now", lambda: clock[0])
    monkeypatch.setattr(circuit, "resolve_redis_client", lambda: None)

    first = await circuit.before_provider_probe("truenas:api")
    first_meta = await circuit.record_provider_probe_outcome(first, success=False)
    await circuit.release_provider_probe(first)

    second = await circuit.before_provider_probe("truenas:api")
    second_meta = await circuit.record_provider_probe_outcome(second, success=False)
    await circuit.release_provider_probe(second)

    blocked = await circuit.before_provider_probe("truenas:api")

    assert first_meta["state"] == "closed"
    assert first_meta["failures"] == 1
    assert second_meta["state"] == "open"
    assert second_meta["failures"] == 2
    assert second_meta["retry_after_seconds"] == 10
    assert blocked.allowed is False
    assert blocked.metadata(origin_suppressed=True)["origin_suppressed"] is True

    clock[0] += 11.0
    half_open = await circuit.before_provider_probe("truenas:api")
    assert half_open.allowed is True
    assert half_open.half_open is True
    recovered = await circuit.record_provider_probe_outcome(half_open, success=True)
    await circuit.release_provider_probe(half_open)

    assert recovered["state"] == "closed"
    assert recovered["failures"] == 0
    await circuit.reset_provider_circuit_for_probe_key("truenas:api")


@pytest.mark.asyncio
async def test_half_open_allows_only_one_local_probe(monkeypatch) -> None:
    await circuit.reset_provider_circuits()
    clock = [2_000.0]
    policy = circuit.CircuitBreakerPolicy(
        failure_threshold=1,
        base_backoff=5.0,
        max_backoff=10.0,
        jitter_ratio=0.0,
    )
    monkeypatch.setitem(circuit._PROVIDER_POLICIES, "pfsense", policy)
    monkeypatch.setattr(circuit, "_now", lambda: clock[0])
    monkeypatch.setattr(circuit, "resolve_redis_client", lambda: None)

    initial = await circuit.before_provider_probe("pfsense:liveness")
    await circuit.record_provider_probe_outcome(initial, success=False)
    clock[0] += 6.0

    first_half_open = await circuit.before_provider_probe("pfsense:posture")
    duplicate = await circuit.before_provider_probe("pfsense:snort2c")

    assert first_half_open.allowed is True
    assert first_half_open.half_open is True
    assert duplicate.allowed is False
    assert duplicate.half_open is True

    await circuit.record_provider_probe_outcome(first_half_open, success=True)
    await circuit.release_provider_probe(first_half_open)
    await circuit.reset_provider_circuit_for_probe_key("pfsense:liveness")


@pytest.mark.asyncio
async def test_redis_shares_open_circuit_across_local_reset(monkeypatch) -> None:
    redis = FakeRedis()
    await circuit.reset_provider_circuits()
    clock = [3_000.0]
    policy = circuit.CircuitBreakerPolicy(
        failure_threshold=2,
        base_backoff=30.0,
        max_backoff=60.0,
        jitter_ratio=0.0,
    )
    monkeypatch.setitem(circuit._PROVIDER_POLICIES, "truenas", policy)
    monkeypatch.setattr(circuit, "_now", lambda: clock[0])

    for _ in range(2):
        decision = await circuit.before_provider_probe(
            "truenas:api",
            redis_client=redis,
        )
        await circuit.record_provider_probe_outcome(decision, success=False)
        await circuit.release_provider_probe(decision)

    await circuit.reset_provider_circuits()
    replica = await circuit.before_provider_probe(
        "truenas:api",
        redis_client=redis,
    )

    assert replica.allowed is False
    assert replica.redis_available is True
    metadata = replica.metadata(origin_suppressed=True)
    assert metadata["state"] == "open"
    assert metadata["failures"] == 2
    assert metadata["redis_shared"] is True
    await circuit.reset_provider_circuit_for_probe_key(
        "truenas:api",
        redis_client=redis,
    )
