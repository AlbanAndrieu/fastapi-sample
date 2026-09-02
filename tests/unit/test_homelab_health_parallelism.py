"""Concurrency regressions for the homelab health refresh path."""

import asyncio

import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


@pytest.mark.asyncio
async def test_internal_probes_run_while_truenas_probe_is_pending(monkeypatch) -> None:
    """A slow TrueNAS probe must not serialize independent internal probes."""
    release_truenas = asyncio.Event()
    internal_started = asyncio.Event()
    services = [
        HomelabService(
            name="Internal service",
            internalHost="192.0.2.10",
            internalPort=8443,
            external=False,
        )
    ]

    async def fake_truenas_probe(*_args, **_kwargs):
        await release_truenas.wait()
        return {
            "state": "ok",
            "public": {"state": "ok"},
            "internal": None,
            "internal_probe_enabled": True,
        }

    async def fake_internal_probe(_semaphore, service):
        internal_started.set()
        release_truenas.set()
        return {
            "id": service.service_id,
            "name": service.name,
            "host": service.internal_host,
            "port": service.internal_port,
            "reachable": True,
            "state": "ok",
            "latency_ms": 1,
        }

    async def fake_services():
        return services

    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", "true")
    monkeypatch.setattr(homelab_health, "fetch_homelab_services", fake_services)
    monkeypatch.setattr(homelab_health, "_probe_truenas", fake_truenas_probe)
    monkeypatch.setattr(homelab_health, "_probe_internal_service", fake_internal_probe)
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)

    payload = await asyncio.wait_for(
        homelab_health.build_homelab_health_payload(),
        timeout=1.0,
    )

    assert internal_started.is_set()
    assert payload["truenas"]["state"] == "ok"
    assert payload["internal_services"][0]["reachable"] is True
    assert payload["refresh_elapsed_ms"] >= 0
