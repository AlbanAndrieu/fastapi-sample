"""Deterministic regressions for bounded homelab probe fan-out."""

from __future__ import annotations

import asyncio

import pytest

from nabla.api import homelab_health, homelab_probe_policy
from nabla.api.homelab_models import HomelabService


def _service(index: int) -> HomelabService:
    return HomelabService(
        id=f"service-{index}",
        name=f"Service {index}",
        internalHost="172.17.0.24",
        internalPort=20_000 + index,
        tunnelUrl=f"https://service-{index}.albandrieu.com",
        external=True,
    )


@pytest.mark.asyncio
async def test_production_scale_catalog_keeps_probe_fanout_bounded_and_cached(
    monkeypatch,
) -> None:
    services = [_service(index) for index in range(96)]
    public_started: list[str] = []
    internal_started: list[str] = []
    active = 0
    max_active = 0

    async def enter_probe(semaphore: asyncio.Semaphore) -> None:
        nonlocal active, max_active
        await semaphore.acquire()
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.001)

    def leave_probe(semaphore: asyncio.Semaphore) -> None:
        nonlocal active
        active -= 1
        semaphore.release()

    async def public_probe(_client, semaphore, service):
        public_started.append(service.service_id)
        await enter_probe(semaphore)
        leave_probe(semaphore)
        return {
            "id": service.service_id,
            "name": service.name,
            "url": service.public_https_probe_url,
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 1,
        }

    async def internal_probe(semaphore, service):
        internal_started.append(service.service_id)
        await enter_probe(semaphore)
        leave_probe(semaphore)
        return {
            "id": service.service_id,
            "name": service.name,
            "host": service.internal_host,
            "port": service.internal_port,
            "reachable": True,
            "state": "ok",
            "latency_ms": 1,
        }

    async def truenas_probe(_semaphore, *, internal_enabled):
        return {
            "state": "ok",
            "public": {"state": "ok"},
            "internal": {"state": "ok"} if internal_enabled else None,
            "internal_probe_enabled": internal_enabled,
        }

    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", "true")
    monkeypatch.setattr(homelab_health, "_probe_public_service", public_probe)
    monkeypatch.setattr(homelab_health, "_probe_internal_service", internal_probe)
    monkeypatch.setattr(homelab_health, "_probe_truenas", truenas_probe)
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)

    first = await homelab_health.build_homelab_health_payload(
        catalog_services=services,
    )
    second = await homelab_health.build_homelab_health_payload(
        catalog_services=services,
    )

    assert len(public_started) == homelab_probe_policy.MAX_PUBLIC_PROBES_PER_REFRESH
    assert len(internal_started) == homelab_probe_policy.MAX_INTERNAL_PROBES_PER_REFRESH
    assert len(set(public_started)) == len(public_started)
    assert len(set(internal_started)) == len(internal_started)
    assert max_active <= homelab_probe_policy.MAX_PROBE_CONCURRENCY
    assert first["probe_summary"]["public"]["eligible"] == 96
    assert first["probe_summary"]["public"]["sampled"] == 12
    assert first["probe_summary"]["internal"]["eligible"] == 96
    assert first["probe_summary"]["internal"]["sampled"] == 12
    assert first["refresh_elapsed_ms"] < 4_000
    assert second["probe_cache"]["source"] == "memory"
    assert len(public_started) == 12
    assert len(internal_started) == 12


@pytest.mark.asyncio
async def test_fanout_deadline_cancels_queued_probes_without_late_burst(
    monkeypatch,
) -> None:
    services = [_service(index) for index in range(24)]
    semaphore = asyncio.Semaphore(homelab_probe_policy.MAX_PROBE_CONCURRENCY)
    blocker = asyncio.Event()
    started: list[str] = []

    async def blocked_probe(service: HomelabService) -> dict[str, object]:
        async with semaphore:
            started.append(service.service_id)
            await blocker.wait()
        return {
            "id": service.service_id,
            "name": service.name,
            "state": "ok",
        }

    monkeypatch.setattr(homelab_health, "_SERVICE_FANOUT_BUDGET_SEC", 0.01)
    probes = [
        (service, asyncio.create_task(blocked_probe(service)))
        for service in services
    ]

    results, summary = await homelab_health._collect_bounded_probe_batch(
        probes,
        scope="internal",
    )

    assert len(started) == homelab_probe_policy.MAX_PROBE_CONCURRENCY
    assert summary["scheduled"] == 24
    assert summary["completed"] == 0
    assert summary["timed_out"] == 24
    assert all(result["timed_out"] is True for result in results)

    blocker.set()
    await asyncio.sleep(0.02)
    assert len(started) == homelab_probe_policy.MAX_PROBE_CONCURRENCY
