"""Regression tests for non-blocking declared/topology stale-while-revalidate."""

from __future__ import annotations

import asyncio

import pytest

from nabla.api import homelab_declared, homelab_topology
from nabla.api.homelab_declared import DeclaredServiceCatalog
from nabla.api.homelab_topology import HomelabTopology


@pytest.mark.asyncio
async def test_declared_catalog_serves_stale_while_single_refresh_runs(
    monkeypatch,
) -> None:
    stale = DeclaredServiceCatalog(
        version=1,
        catalogRevision="sha256:" + "a" * 64,
        topologyVersion=1,
        name="stale",
    )
    fresh = DeclaredServiceCatalog(
        version=1,
        catalogRevision="sha256:" + "b" * 64,
        topologyVersion=1,
        name="fresh",
    )
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def origin() -> DeclaredServiceCatalog:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return fresh

    monkeypatch.setattr(homelab_declared._cache, "catalog", stale)
    monkeypatch.setattr(homelab_declared._cache, "at", 0.0)
    monkeypatch.setattr(homelab_declared._cache, "refresh_task", None)
    monkeypatch.setattr(
        homelab_declared,
        "_fetch_declared_service_catalog_origin",
        origin,
    )

    first, second = await asyncio.gather(
        homelab_declared.fetch_declared_service_catalog(),
        homelab_declared.fetch_declared_service_catalog(),
    )

    assert first is stale
    assert second is stale

    task = homelab_declared._cache.refresh_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=5.0)
    assert calls == 1

    release.set()
    assert await asyncio.wait_for(task, timeout=5.0) is fresh
    assert await homelab_declared.fetch_declared_service_catalog() is fresh


@pytest.mark.asyncio
async def test_topology_serves_stale_while_single_refresh_runs(monkeypatch) -> None:
    stale = HomelabTopology(name="stale")
    fresh = HomelabTopology(name="fresh")
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def origin() -> HomelabTopology:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return fresh

    monkeypatch.setattr(homelab_topology._topology_cache, "topology", stale)
    monkeypatch.setattr(homelab_topology._topology_cache, "cached_at", 0.0)
    monkeypatch.setattr(homelab_topology._topology_cache, "refresh_task", None)
    monkeypatch.setattr(
        homelab_topology,
        "_fetch_homelab_topology_origin",
        origin,
    )

    first, second = await asyncio.gather(
        homelab_topology.fetch_homelab_topology(),
        homelab_topology.fetch_homelab_topology(),
    )

    assert first is stale
    assert second is stale

    task = homelab_topology._topology_cache.refresh_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=5.0)
    assert calls == 1

    release.set()
    assert await asyncio.wait_for(task, timeout=5.0) is fresh
    assert await homelab_topology.fetch_homelab_topology() is fresh

@pytest.mark.asyncio
async def test_topology_uses_packaged_snapshot_on_cold_start_failure(monkeypatch) -> None:
    packaged = HomelabTopology(
        name="packaged",
        nodes=[],
        relations=[],
    )

    async def failing_origin() -> HomelabTopology:
        raise RuntimeError("origin unavailable")

    monkeypatch.setattr(homelab_topology._topology_cache, "topology", None)
    monkeypatch.setattr(homelab_topology._topology_cache, "cached_at", 0.0)
    monkeypatch.setattr(homelab_topology._topology_cache, "refresh_task", None)
    monkeypatch.setattr(
        homelab_topology,
        "_fetch_homelab_topology_origin",
        failing_origin,
    )
    monkeypatch.setattr(homelab_topology, "_load_packaged_topology", lambda: packaged)

    assert await homelab_topology.fetch_homelab_topology() is packaged

