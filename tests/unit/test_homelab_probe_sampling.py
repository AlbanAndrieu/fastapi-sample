"""Regression tests for bounded rotating homelab service probes."""

from __future__ import annotations

from nabla.api import homelab_health
from nabla.api import homelab_probe_policy
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

    first = homelab_probe_policy.select_probe_subset(
        services,
        limit=12,
        now=0.0,
    )
    second = homelab_probe_policy.select_probe_subset(
        services,
        limit=12,
        now=31.0,
    )

    first_ids = {service.service_id for service in first}
    second_ids = {service.service_id for service in second}
    assert len(first) == 12
    assert len(second) == 12
    assert {"postgresql", "redis"} <= first_ids
    assert {"postgresql", "redis"} <= second_ids
    assert first_ids != second_ids


def test_probe_subset_deduplicates_service_ids_before_sampling() -> None:
    first = _service("duplicate", 20001)
    duplicate = _service("duplicate", 29999)
    services = [
        first,
        duplicate,
        *[_service(f"service-{index}", 21000 + index) for index in range(20)],
    ]

    selected = homelab_probe_policy.select_probe_subset(
        services,
        limit=12,
        now=0.0,
    )

    selected_ids = [service.service_id for service in selected]
    assert len(selected_ids) == len(set(selected_ids)) == 12
    chosen = next(service for service in selected if service.service_id == "duplicate")
    assert chosen.internal_port == first.internal_port


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
    assert homelab_probe_policy.MAX_PROBE_CONCURRENCY == 4
    assert homelab_probe_policy.MAX_INTERNAL_PROBES_PER_REFRESH == 12
    assert homelab_probe_policy.MAX_PUBLIC_PROBES_PER_REFRESH == 12
    assert homelab_probe_policy.INTERNAL_PROBE_TIMEOUT_SEC == 1.0
    assert homelab_probe_policy.PUBLIC_PROBE_TIMEOUT_SEC == 3.0
    assert homelab_probe_policy.SERVICE_FANOUT_BUDGET_SEC == 4.0


def test_garage_private_apis_remain_in_internal_sampling_under_load() -> None:
    services = [
        _service("garage", 3900),
        _service("garage-admin", 3903),
        _service("garage-webui", 3909),
        *[_service(f"background-{index}", 22000 + index) for index in range(80)],
    ]

    for now in (0.0, 31.0, 300.0):
        selected = homelab_probe_policy.select_probe_subset(
            services,
            limit=homelab_probe_policy.MAX_INTERNAL_PROBES_PER_REFRESH,
            now=now,
        )
        assert {"garage", "garage-admin", "garage-webui"} <= {
            item.service_id for item in selected
        }
        assert len(selected) == homelab_probe_policy.MAX_INTERNAL_PROBES_PER_REFRESH


def test_private_garage_is_not_eligible_for_public_probing() -> None:
    admin = _service("garage-admin", 3903)
    s3 = _service("garage", 3900)
    assert admin.external is False
    assert s3.external is False
    assert admin.public_https_probe_url is None
    assert s3.public_https_probe_url is None


def test_full_priority_budget_never_starves_unrelated_services() -> None:
    priority_ids = [
        "postgresql", "redis", "n8n", "prometheus", "grafana", "sentry",
        "pyroscope", "cloudflared", "garage-admin", "vaultwarden",
        "garage", "garage-webui",
    ]
    services = [
        *[_service(service_id, 23000 + i) for i, service_id in enumerate(priority_ids)],
        *[_service(f"background-{i}", 24000 + i) for i in range(16)],
    ]
    selections = [
        homelab_probe_policy.select_probe_subset(services, limit=12, now=30.0 * i)
        for i in range(14)
    ]
    assert all(len(batch) == 12 for batch in selections)
    assert all(
        {"garage", "garage-admin", "garage-webui"}
        <= {service.service_id for service in batch}
        for batch in selections
    )
    assert any(
        service.service_id.startswith("background-")
        for batch in selections
        for service in batch
    )
    assert {
        service.service_id for batch in selections for service in batch
    } == {service.service_id for service in services}
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[-1], eligible_services=services, limit=12
        )
        is not None
    )


def test_empty_probe_budget_is_safe() -> None:
    services = [_service("garage", 3900)]
    assert homelab_probe_policy.select_probe_subset(services, limit=0) == []
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[0], eligible_services=services, limit=0
        )
        is None
    )
