"""Regression tests for bounded rotating homelab service probes."""

from __future__ import annotations

from pathlib import Path

import pytest

from nabla.api import homelab_health
from nabla.api import homelab_probe_policy
from nabla.api import homelab_probe_evidence
from nabla.api.homelab_catalog import _apply_exposure_overrides
from nabla.api.homelab_models import HomelabService


def _service(service_id: str, port: int, *, priority: int | None = None) -> HomelabService:
    return HomelabService(
        id=service_id,
        name=service_id,
        internalHost="172.17.0.24",
        internalPort=port,
        external=False,
        probePriority=priority,
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
        assert {"garage", "garage-admin", "garage-webui"} <= {item.service_id for item in selected}
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
        "postgresql",
        "redis",
        "n8n",
        "prometheus",
        "grafana",
        "sentry",
        "pyroscope",
        "cloudflared",
        "garage-admin",
        "vaultwarden",
        "garage",
        "garage-webui",
    ]
    services = [
        *[_service(service_id, 23000 + i) for i, service_id in enumerate(priority_ids)],
        *[_service(f"background-{i}", 24000 + i) for i in range(16)],
    ]
    selections = [homelab_probe_policy.select_probe_subset(services, limit=12, now=30.0 * i) for i in range(14)]
    assert all(len(batch) == 12 for batch in selections)
    assert all({"garage", "garage-admin", "garage-webui"} <= {service.service_id for service in batch} for batch in selections)
    assert any(service.service_id.startswith("background-") for batch in selections for service in batch)
    assert {service.service_id for batch in selections for service in batch} == {service.service_id for service in services}
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[-1],
            eligible_services=services,
            limit=12,
        )
        is not None
    )


def test_empty_probe_budget_is_safe() -> None:
    services = [_service("garage", 3900)]
    assert homelab_probe_policy.select_probe_subset(services, limit=0) == []
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[0],
            eligible_services=services,
            limit=0,
        )
        is None
    )


def test_small_probe_budgets_keep_rotation_math_safe() -> None:
    services = [
        _service("garage", 3900),
        _service("garage-admin", 3903),
        _service("garage-webui", 3909),
        *[_service(f"background-{index}", 25000 + index) for index in range(4)],
    ]

    one_slot = homelab_probe_policy.select_probe_subset(services, limit=1, now=0.0)
    assert len(one_slot) == 1
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[-1],
            eligible_services=services,
            limit=1,
        )
        is None
    )

    four_slots = homelab_probe_policy.select_probe_subset(services, limit=4, now=0.0)
    assert len(four_slots) == 4
    assert {"garage", "garage-admin", "garage-webui"} <= {item.service_id for item in four_slots}
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[-1],
            eligible_services=services,
            limit=4,
        )
        is not None
    )


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_saturated_tiny_budgets_report_no_rotation_interval(limit: int) -> None:
    services = [
        _service("garage", 3900),
        _service("postgresql", 5432),
        _service("redis", 6379),
        _service("background-0", 26000),
    ]

    selected = homelab_probe_policy.select_probe_subset(services, limit=limit, now=0.0)

    assert [item.service_id for item in selected] == ["garage", "postgresql", "redis"][:limit]
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[-1],
            eligible_services=services,
            limit=limit,
        )
        is None
    )


def test_priority_overflow_is_ranked_and_independent_of_catalog_order() -> None:
    ranked = list(homelab_probe_policy._PRIORITY_SERVICE_ORDER)
    background = [_service(f"background-{i}", 27000 + i) for i in range(16)]
    catalog_orders = [ranked, list(reversed(ranked)), sorted(ranked)]

    for order in catalog_orders:
        services = [*[_service(service_id, 28000 + i) for i, service_id in enumerate(order)], *background]

        selected = homelab_probe_policy.select_probe_subset(services, limit=12, now=0.0)
        rotated = homelab_probe_policy.rotated_priority_ids(services, limit=12)

        assert [item.service_id for item in selected[:10]] == ranked[:10]
        assert rotated == ["n8n", "pyroscope"]
        for service_id in rotated:
            demoted = next(item for item in services if item.service_id == service_id)
            assert (
                homelab_probe_policy.estimated_probe_interval_seconds(
                    demoted,
                    eligible_services=services,
                    limit=12,
                )
                == homelab_probe_policy.HEALTH_CACHE_TTL_SEC * 9
            )


def test_rotated_priority_ids_empty_when_budget_fits() -> None:
    services = [_service("garage", 3900), _service("n8n", 5678)]

    assert homelab_probe_policy.rotated_priority_ids(services, limit=12) == []
    assert homelab_probe_policy.rotated_priority_ids(services, limit=0) == []


def test_evidence_coverage_excludes_stale_and_deadline_samples() -> None:
    rows = [
        {"id": "garage", "probe_source": "origin", "probe_stale": False},
        {"id": "garage-admin", "probe_source": "memory", "probe_stale": False},
        {"id": "garage-webui", "probe_source": "memory", "probe_stale": True},
        {"id": "other", "probe_source": "deadline", "probe_stale": False},
    ]
    summary = homelab_probe_evidence.evidence_summary(rows, eligible_count=4)
    assert summary["fresh"] == 1
    assert summary["cached"] == 1
    assert summary["stale"] == 1
    assert summary["known"] == 2
    assert summary["coverage_percent"] == 50.0


def test_catalog_probe_priority_replaces_bootstrap_order() -> None:
    services = [
        _service("garage", 3900),
        _service("garage-admin", 3903),
        *[_service(f"background-{i}", 29000 + i, priority=20 - i) for i in range(3)],
        *[_service(f"filler-{i}", 29100 + i) for i in range(20)],
    ]

    selected = homelab_probe_policy.select_probe_subset(services, limit=12, now=0.0)

    assert homelab_probe_policy.priority_source(services) == "catalog"
    assert [item.service_id for item in selected[:3]] == ["background-2", "background-1", "background-0"]
    assert homelab_probe_policy.rotated_priority_ids(services, limit=12) == []
    assert (
        homelab_probe_policy.estimated_probe_interval_seconds(
            services[0],
            eligible_services=services,
            limit=12,
        )
        != homelab_probe_policy.HEALTH_CACHE_TTL_SEC
    )


def test_catalog_priority_overflow_rotates_highest_ranks_last() -> None:
    services = [_service(f"ranked-{i}", 29200 + i, priority=i) for i in range(12)]
    services += [_service(f"filler-{i}", 29300 + i) for i in range(4)]

    selected = homelab_probe_policy.select_probe_subset(services, limit=12, now=0.0)

    assert [item.service_id for item in selected[:10]] == [f"ranked-{i}" for i in range(10)]
    assert homelab_probe_policy.rotated_priority_ids(services, limit=12) == ["ranked-10", "ranked-11"]


def test_bootstrap_order_applies_without_catalog_priority() -> None:
    services = [_service("n8n", 5678), _service("garage", 3900)]

    assert homelab_probe_policy.priority_source(services) == "bootstrap"
    assert [item.service_id for item in homelab_probe_policy._ranked_priorities(services)] == ["garage", "n8n"]


@pytest.mark.parametrize("invalid", [True, -1, 1001, "1"])
def test_probe_priority_rejects_non_integer_ranks(invalid: object) -> None:
    with pytest.raises(ValueError):
        HomelabService(id="garage", name="garage", probePriority=invalid)


def test_exposure_override_propagates_probe_priority() -> None:
    merged = _apply_exposure_overrides(
        {"services": [{"id": "garage", "name": "Garage S3 API"}]},
        {"services": [{"name": "Garage S3 API", "probePriority": 0}]},
    )

    assert merged["services"][0]["probePriority"] == 0
    assert HomelabService.model_validate(merged["services"][0]).probe_priority == 0


def test_catalog_coverage_is_distinct_from_rotating_probe_slots():
    source = (Path(__file__).resolve().parents[2] / "nabla/api/homelab_health.py").read_text()
    assert '"catalog_observable_service_count"' in source
    assert '"catalog_unconfigured_service_count"' in source
    assert '"internal_disabled_eligible_slots"' in source
    assert '"unsampled_current_window"' in source
    assert "catalog_ids - monitored_ids" in source


def test_curated_public_cards_exclude_private_garage_apis() -> None:
    path = Path(__file__).resolve().parents[2] / "nabla/api/homelab_health.py"
    source = path.read_text(encoding="utf-8")
    assert '"public_card_candidates": public_cards' in source
    assert '"gatus": "Gatus"' in source
    assert '"garage-webui": "Garage Web UI"' in source
    assert '"garage-admin": "Garage Admin API"' not in source
