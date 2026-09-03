"""Unit tests for the request-scoped probe budget."""

import asyncio

import pytest

from nabla.api import probe_budget


def test_probe_budget_validates_limits() -> None:
    with pytest.raises(ValueError):
        probe_budget.ProbeBudget(deadline_seconds=0.0, max_concurrency=1)
    with pytest.raises(ValueError):
        probe_budget.ProbeBudget(deadline_seconds=1.0, max_concurrency=0)


@pytest.mark.asyncio
async def test_expired_budget_skips_origin(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr(probe_budget, "_now", lambda: clock[0])
    budget = probe_budget.ProbeBudget(deadline_seconds=5.0, max_concurrency=1)
    clock[0] = 106.0
    started = False

    async def origin() -> str:
        nonlocal started
        started = True
        return "origin"

    result = await budget.run(origin, timeout_value=lambda: "timeout")

    assert result == "timeout"
    assert started is False


@pytest.mark.asyncio
async def test_probe_budget_caps_concurrency() -> None:
    budget = probe_budget.ProbeBudget(deadline_seconds=2.0, max_concurrency=2)
    release = asyncio.Event()
    two_started = asyncio.Event()
    running = 0
    peak = 0

    async def origin() -> str:
        nonlocal peak, running
        running += 1
        peak = max(peak, running)
        if running == 2:
            two_started.set()
        await release.wait()
        running -= 1
        return "ok"

    tasks = [
        asyncio.create_task(budget.run(origin, timeout_value=lambda: "timeout"))
        for _ in range(3)
    ]
    await asyncio.wait_for(two_started.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert peak == 2

    release.set()
    assert await asyncio.gather(*tasks) == ["ok", "ok", "ok"]
    assert peak == 2
