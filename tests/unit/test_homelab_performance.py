"""Contracts for fixed-cardinality homelab health performance telemetry."""

import asyncio

import pytest

from nabla.api import homelab_health_evidence as evidence
from nabla.api.homelab_performance import (
    HOMELAB_HEALTH_PERF_PHASES,
    dominant_homelab_phase,
    finalize_homelab_performance,
    record_homelab_phase,
    timed_homelab_phase,
)


def test_phase_labels_are_fixed_and_operator_facing() -> None:
    assert HOMELAB_HEALTH_PERF_PHASES == (
        "declared_catalog",
        "topology",
        "cloudflare_exposure",
        "pfsense_posture",
        "truenas_runtime",
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


def test_finalize_exposes_all_fixed_phases_without_dynamic_labels() -> None:
    payload = {
        "performance": {
            "phases_ms": {
                "declared_catalog": 12.3,
                "reconciliation": 4.2,
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
    assert performance["dominant_phase"] == "declared_catalog"
    assert performance["dominant_phase_ms"] == 12.3


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
