"""Contracts for fixed-cardinality homelab health performance telemetry."""

import asyncio

import pytest

from nabla.api import health_board, homelab_catalog, homelab_health
from nabla.api import homelab_health_evidence as evidence
from nabla.api.homelab_performance import (
    HOMELAB_HEALTH_PERF_PHASES,
    HOMELAB_HEALTH_PROVIDER_PHASES,
    dominant_homelab_phase,
    dominant_homelab_provider_phase,
    finalize_homelab_performance,
    record_homelab_phase,
    timed_homelab_phase,
)
from nabla.api.homelab_topology import HomelabTopology


def test_phase_labels_are_fixed_and_operator_facing() -> None:
    assert HOMELAB_HEALTH_PROVIDER_PHASES == (
        "declared_catalog",
        "topology",
        "cloudflare_exposure",
        "pfsense_posture",
        "truenas_runtime",
    )
    assert HOMELAB_HEALTH_PERF_PHASES == (
        *HOMELAB_HEALTH_PROVIDER_PHASES,
        "reconciliation",
        "total",
    )


def test_unknown_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported homelab health phase"):
        record_homelab_phase({}, "service:https://example.invalid", 0.1)


def test_dominant_phase_ignores_total_and_missing_values() -> None:
    phase, duration_ms = dominant_homelab_phase(
        {
            "declared_catalog": 12.3,
            "topology": None,
            "cloudflare_exposure": 8.1,
            "reconciliation": 18.4,
            "total": 500.0,
        },
    )

    assert phase == "reconciliation"
    assert duration_ms == 18.4
    assert dominant_homelab_phase({"total": 10.0}) == (None, None)


def test_dominant_provider_excludes_reconciliation_orchestration() -> None:
    phase, duration_ms = dominant_homelab_provider_phase(
        {
            "declared_catalog": 12.3,
            "cloudflare_exposure": 81.2,
            "pfsense_posture": 42.0,
            "reconciliation": 180.0,
            "total": 500.0,
        },
    )

    assert phase == "cloudflare_exposure"
    assert duration_ms == 81.2
    assert dominant_homelab_provider_phase({"reconciliation": 10.0}) == (None, None)


def test_finalize_exposes_all_fixed_phases_without_dynamic_labels() -> None:
    payload = {
        "performance": {
            "phases_ms": {
                "declared_catalog": 12.3,
                "cloudflare_exposure": 9.1,
                "reconciliation": 44.2,
            },
        },
    }
    result = finalize_homelab_performance(payload, total_seconds=0.123)
    performance = result["performance"]
    assert performance["fixed_cardinality"] is True
    assert performance["phase_count"] == 7
    assert tuple(performance["phases_ms"]) == HOMELAB_HEALTH_PERF_PHASES
    assert performance["phases_ms"]["total"] == 123.0
    assert performance["phases_ms"]["topology"] is None
    assert performance["dominant_phase"] == "reconciliation"
    assert performance["dominant_phase_ms"] == 44.2
    assert performance["dominant_provider_phase"] == "declared_catalog"
    assert performance["dominant_provider_phase_ms"] == 12.3


def test_timed_phase_preserves_result_and_records_duration() -> None:
    timings: dict[str, float] = {}

    async def provider() -> str:
        await asyncio.sleep(0)
        return "ok"

    assert asyncio.run(timed_homelab_phase("topology", provider(), timings)) == "ok"
    assert timings["topology"] >= 0


def test_provider_context_keeps_all_four_reads_parallel(monkeypatch) -> None:
    started: set[str] = set()
    gate = asyncio.Event()

    async def provider(name: str):
        started.add(name)
        if len(started) == 4:
            gate.set()
        await asyncio.wait_for(gate.wait(), timeout=0.5)
        return name

    async def declared():
        return await provider("declared")

    async def cloudflare():
        return await provider("cloudflare")

    async def topology():
        return await provider("topology")

    async def pfsense(**_kwargs):
        return await provider("pfsense")

    monkeypatch.setattr(evidence, "fetch_declared_service_catalog", declared)
    monkeypatch.setattr(evidence, "observe_cloudflare_exposure", cloudflare)
    monkeypatch.setattr(evidence, "fetch_homelab_topology", topology)
    monkeypatch.setattr(evidence, "observe_pfsense_dns_posture", pfsense)

    context = asyncio.run(evidence.prepare_homelab_reconciliation_context([]))

    assert started == {"declared", "cloudflare", "topology", "pfsense"}
    assert set(context["performance_phases_ms"]) == {
        "declared_catalog",
        "cloudflare_exposure",
        "topology",
        "pfsense_posture",
    }
    assert all(value >= 0 for value in context["performance_phases_ms"].values())


@pytest.mark.asyncio
async def test_homelab_aggregate_reads_each_reconciliation_provider_once(
    monkeypatch,
) -> None:
    calls = {"declared": 0, "cloudflare": 0, "topology": 0, "pfsense": 0}

    class Catalog:
        services = []

    class Cloudflare:
        tunnels = []
        access_applications = []
        stale = False
        configured = True

        def summary(self):
            return {
                "configured": True,
                "status_confirmed": True,
                "warning": None,
            }

    async def services():
        return []

    async def declared():
        calls["declared"] += 1
        return Catalog()

    async def cloudflare():
        calls["cloudflare"] += 1
        return Cloudflare()

    async def topology():
        calls["topology"] += 1
        return HomelabTopology()

    async def pfsense(**_kwargs):
        calls["pfsense"] += 1
        return {
            "configured": True,
            "reachable": True,
            "policy_state": "ok",
            "resolver": {"enabled": True, "running": True},
        }

    async def truenas(_semaphore, *, internal_enabled):
        return {
            "state": "ok",
            "public": {"state": "ok", "reachable": True, "tls_trusted": True},
            "internal": None,
            "api": {"reachable": True, "stale": False, "apps": []},
            "internal_probe_enabled": internal_enabled,
        }

    monkeypatch.setattr(homelab_catalog, "fetch_homelab_services", services)
    monkeypatch.setattr(homelab_health, "_probe_truenas", truenas)
    monkeypatch.setattr(homelab_health, "_cached_payload", None)
    monkeypatch.setattr(homelab_health, "_cached_at", 0.0)
    monkeypatch.setattr(evidence, "fetch_declared_service_catalog", declared)
    monkeypatch.setattr(evidence, "observe_cloudflare_exposure", cloudflare)
    monkeypatch.setattr(evidence, "fetch_homelab_topology", topology)
    monkeypatch.setattr(evidence, "observe_pfsense_dns_posture", pfsense)

    payload = await health_board._build_homelab_snapshot(
        {
            "postgres": {"reachable": True},
            "redis": {"reachable": True},
            "supabase": {"reachable": True},
            "cloudflare": {"reachable": True, "status_confirmed": True},
            "pfsense": {"reachable": True, "status_confirmed": True},
        },
    )

    assert calls == {"declared": 1, "cloudflare": 1, "topology": 1, "pfsense": 1}
    assert payload["reconciliation"]["provider_reads_reused"] is True
    assert payload["performance"]["dominant_provider_phase"] in HOMELAB_HEALTH_PROVIDER_PHASES
    assert payload["performance"]["dominant_provider_phase_ms"] is not None
    assert payload["performance"]["phases_ms"]["total"] < 1_000
