"""Regression tests for bounded rotating homelab service probes."""

from __future__ import annotations

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


def _service(service_id: str, port: int) -> HomelabService:
    return HomelabService(
        id=service_id,
        name=service_id,
        internalHost="172.17.0.24",
        internalPort=port,
        external=False,
    )


def test_probe_subset_keeps_priority_services_and_rotates_remainder(
    monkeypatch,
) -> None:
    services = [
        _service("postgresql", 5432),
        _service("redis", 6379),
        *[_service(f"service-{index}", 20000 + index) for index in range(20)],
    ]

    monkeypatch.setattr(homelab_health.time, "monotonic", lambda: 0.0)
    first = homelab_health._select_probe_subset(services, limit=12)

    monkeypatch.setattr(homelab_health.time, "monotonic", lambda: 31.0)
    second = homelab_health._select_probe_subset(services, limit=12)

    first_ids = {service.service_id for service in first}
    second_ids = {service.service_id for service in second}
    assert len(first) == 12
    assert len(second) == 12
    assert {"postgresql", "redis"} <= first_ids
    assert {"postgresql", "redis"} <= second_ids
    assert first_ids != second_ids


def test_probe_cache_metadata_exposes_source_age_and_ttl() -> None:
    payload = {
        "truenas": {},
        "services": [],
        "public_probe_results": [],
        "internal_services": [],
        "probe_summary": {"public": {}, "internal": {}},
    }

    copied = homelab_health._copy_payload(
        payload,
        cache_source="memory",
        cache_age_seconds=12.4,
    )

    assert copied["probe_cache"] == {
        "source": "memory",
        "age_seconds": 12.4,
        "ttl_seconds": 30.0,
        "stale": False,
    }


def test_probe_limits_keep_one_refresh_bounded() -> None:
    assert homelab_health._MAX_PROBE_CONCURRENCY == 4
    assert homelab_health._MAX_INTERNAL_PROBES_PER_REFRESH == 12
    assert homelab_health._MAX_PUBLIC_PROBES_PER_REFRESH == 12
    assert homelab_health._INTERNAL_PROBE_TIMEOUT_SEC == 1.0
    assert homelab_health._PUBLIC_PROBE_TIMEOUT_SEC == 3.0
    assert homelab_health._SERVICE_FANOUT_BUDGET_SEC == 4.0
