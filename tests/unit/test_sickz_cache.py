"""The public /sickz route must not repeat its homelab fan-out per request."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from nabla.api import sickz_cache


def _request(host: str = "fastapi-sample.fastapicloud.dev") -> Any:
    return SimpleNamespace(url=SimpleNamespace(hostname=host))


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sickz_cache, "_lock", asyncio.Lock())
    monkeypatch.setattr(sickz_cache, "_snapshot", None)
    monkeypatch.setattr(sickz_cache, "_snapshot_key", None)
    monkeypatch.setattr(sickz_cache, "_cached_at", 0.0)


class _Builder:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, _request: Any) -> dict[str, Any]:
        self.calls += 1
        await asyncio.sleep(0.01)
        return {"checks": {"a": {"policy_status": "ok"}}, "build": self.calls}


@pytest.mark.asyncio
async def test_concurrent_requests_share_one_origin_build() -> None:
    builder = _Builder()

    results = await asyncio.gather(*(sickz_cache.cached_sickz_snapshot(_request(), builder) for _ in range(8)))

    assert builder.calls == 1
    assert sorted(r["probe_cache"]["source"] for r in results) == ["cache"] * 7 + ["origin"]
    assert {r["build"] for r in results} == {1}


@pytest.mark.asyncio
async def test_snapshot_is_rebuilt_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _Builder()
    clock = [1000.0]
    monkeypatch.setattr(sickz_cache, "_now", lambda: clock[0])

    await sickz_cache.cached_sickz_snapshot(_request(), builder)
    clock[0] += sickz_cache.SICKZ_CACHE_TTL_SECONDS - 1
    cached = await sickz_cache.cached_sickz_snapshot(_request(), builder)
    clock[0] += 2
    rebuilt = await sickz_cache.cached_sickz_snapshot(_request(), builder)

    assert cached["probe_cache"]["source"] == "cache"
    assert rebuilt["probe_cache"]["source"] == "origin"
    assert builder.calls == 2


@pytest.mark.asyncio
async def test_runtime_scope_is_part_of_the_cache_key() -> None:
    builder = _Builder()

    await sickz_cache.cached_sickz_snapshot(_request("fastapi-sample.fastapicloud.dev"), builder)
    other = await sickz_cache.cached_sickz_snapshot(_request("127.0.0.1"), builder)

    assert other["probe_cache"]["source"] == "origin"
    assert builder.calls == 2


@pytest.mark.asyncio
async def test_cached_copy_cannot_be_mutated_by_callers() -> None:
    builder = _Builder()

    first = await sickz_cache.cached_sickz_snapshot(_request(), builder)
    first["checks"]["a"]["policy_status"] = "tampered"
    second = await sickz_cache.cached_sickz_snapshot(_request(), builder)

    assert second["checks"]["a"]["policy_status"] == "ok"


@pytest.mark.asyncio
async def test_reset_forces_a_new_origin_build() -> None:
    builder = _Builder()

    await sickz_cache.cached_sickz_snapshot(_request(), builder)
    await sickz_cache.reset_sickz_cache()
    again = await sickz_cache.cached_sickz_snapshot(_request(), builder)

    assert again["probe_cache"]["source"] == "origin"
    assert builder.calls == 2


@pytest.mark.asyncio
async def test_builder_failure_is_not_cached() -> None:
    calls = 0

    async def flaky(_request: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("probe fan-out failed")
        return {"checks": {}}

    with pytest.raises(RuntimeError):
        await sickz_cache.cached_sickz_snapshot(_request(), flaky)
    recovered = await sickz_cache.cached_sickz_snapshot(_request(), flaky)

    assert recovered["probe_cache"]["source"] == "origin"
    assert calls == 2
