"""Tests for bounded per-provider origin-probe admission."""

import pytest

from nabla.api import provider_probe_budget as budget


@pytest.mark.asyncio
async def test_local_truenas_budget_allows_two_origin_attempts_per_minute(
    monkeypatch,
) -> None:
    clock = [120.0]
    monkeypatch.setattr(budget, "_now", lambda: clock[0])
    monkeypatch.setattr(budget, "resolve_redis_client", lambda: None)
    await budget.reset_provider_probe_budgets()

    first = await budget.admit_provider_probe("truenas:api")
    second = await budget.admit_provider_probe("truenas:api")
    denied = await budget.admit_provider_probe("truenas:api")

    assert first.allowed is True
    assert second.allowed is True
    assert denied.allowed is False
    assert denied.count == 3
    assert denied.max_requests == 2
    assert denied.redis_shared is False

    clock[0] += 60.0
    next_window = await budget.admit_provider_probe("truenas:api")
    assert next_window.allowed is True
    assert next_window.count == 1

    await budget.reset_provider_probe_budgets()


@pytest.mark.asyncio
async def test_provider_limits_allow_two_complete_declared_cold_starts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(budget, "resolve_redis_client", lambda: None)
    await budget.reset_provider_probe_budgets()

    expected = {
        "truenas:api": 2,
        "pfsense:liveness": 6,
        "cloudflare:tunnels": 4,
    }
    for probe_key, max_requests in expected.items():
        decision = await budget.admit_provider_probe(probe_key)
        assert decision.max_requests == max_requests
        assert decision.window_seconds == 60

    await budget.reset_provider_probe_budgets()


@pytest.mark.asyncio
async def test_unknown_probe_provider_is_not_rate_limited() -> None:
    await budget.reset_provider_probe_budgets()

    for _ in range(20):
        decision = await budget.admit_provider_probe("integration:fixture")
        assert decision.allowed is True
        assert decision.provider is None

    await budget.reset_provider_probe_budgets()


@pytest.mark.asyncio
async def test_redis_failure_keeps_local_budget_authoritative(monkeypatch) -> None:
    class BrokenRedis:
        def pipeline(self, *, transaction: bool):
            del transaction
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(budget, "_now", lambda: 120.0)
    await budget.reset_provider_probe_budgets()

    first = await budget.admit_provider_probe(
        "truenas:api",
        redis_client=BrokenRedis(),  # type: ignore[arg-type]
    )
    second = await budget.admit_provider_probe(
        "truenas:api",
        redis_client=BrokenRedis(),  # type: ignore[arg-type]
    )
    denied = await budget.admit_provider_probe(
        "truenas:api",
        redis_client=BrokenRedis(),  # type: ignore[arg-type]
    )

    assert first.allowed is True
    assert second.allowed is True
    assert denied.allowed is False
    assert denied.redis_shared is False

    await budget.reset_provider_probe_budgets()
