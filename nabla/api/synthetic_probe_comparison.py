"""Internal-probe comparison between the TrueNAS observer and Gatus."""

from __future__ import annotations

import math
from typing import Any

_INTERNAL_TRANSPORT_TYPES = ("TCP",)
_INTERNAL_APPLICATION_TYPES = ("HTTP", "HTTPS")


def _matching_gatus_probe(
    service: dict[str, Any],
    probe_types: tuple[str, ...],
) -> tuple[str, float] | None:
    for probe_type in probe_types:
        evidence = service.get(probe_type)
        if not isinstance(evidence, dict):
            continue
        value = evidence.get("success")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                numeric = float(value)
            except OverflowError:
                continue
            if math.isfinite(numeric) and 0.0 <= numeric <= 1.0:
                return probe_type, numeric
    return None


def _valid_gatus_up(value: object) -> bool:
    """Fail closed on impossible or oversized telemetry samples."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        numeric = float(value)
    except OverflowError:
        return False
    return math.isfinite(numeric) and numeric == 1.0


def _direct_internal_states(homelab: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    """Return deduplicated direct states and IDs with contradictory states."""
    seen_states: dict[str, str] = {}
    conflicting_direct_ids: set[str] = set()
    rows = homelab.get("internal_services")
    if not isinstance(rows, list):
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        service_id = str(row.get("id") or "").strip()
        direct_state = str(row.get("state") or "").strip().lower()
        if not service_id or direct_state not in {"ok", "fail"}:
            continue
        previous = seen_states.setdefault(service_id, direct_state)
        if previous != direct_state:
            conflicting_direct_ids.add(service_id)
    return seen_states, conflicting_direct_ids


def _compare_internal_service(
    counters: dict[str, Any],
    service_id: str,
    direct_state: str,
    synthetic_service: object,
) -> None:
    """Accumulate the comparison outcome for one non-conflicting service."""
    if not isinstance(synthetic_service, dict):
        counters["missing_gatus"] += 1
        counters["missing_gatus_ids"].append(service_id)
        counters["missing_gatus_reasons"][service_id] = "no_labeled_service_metrics"
        return

    transport = _matching_gatus_probe(
        synthetic_service,
        _INTERNAL_TRANSPORT_TYPES,
    )
    if transport is not None:
        probe_type, success = transport
        counters["comparable"] += 1
        direct_up = direct_state == "ok"
        gatus_up = success >= 1.0
        if direct_up == gatus_up:
            counters["matched"] += 1
        else:
            counters["mismatched"] += 1
            counters["mismatches"].append(
                {
                    "id": service_id,
                    "direct_state": direct_state,
                    "gatus_type": probe_type,
                    "gatus_success": success,
                },
            )
        return

    application = _matching_gatus_probe(
        synthetic_service,
        _INTERNAL_APPLICATION_TYPES,
    )
    if application is not None:
        counters["application_evidence"] += 1
        return

    counters["missing_gatus"] += 1
    counters["missing_gatus_ids"].append(service_id)
    counters["missing_gatus_reasons"][service_id] = "no_valid_comparable_probe"


def compare_internal_probe_evidence(
    homelab: dict[str, Any],
    platform_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Compare only internal generic probes; public outside-in probes stay distinct."""

    synthetic = platform_metrics.get("synthetic_probes")
    services = synthetic.get("services") if isinstance(synthetic, dict) else None
    if not isinstance(services, dict) or synthetic.get("state") != "observed":
        return {
            "source": "gatus_via_prometheus",
            "scope": "truenas_internal_only",
            "external_probes_preserved": True,
            "shadow_only": True,
            "state": "unavailable",
            "reason": "synthetic_metrics_not_observed",
            "comparable": 0,
            "matched": 0,
            "mismatched": 0,
            "application_evidence": 0,
            "missing_gatus": 0,
            "missing_gatus_ids": [],
            "missing_gatus_reasons": {},
            "conflicting_direct_ids": [],
            "mismatches": [],
        }

    counters: dict[str, Any] = {
        "comparable": 0,
        "matched": 0,
        "mismatched": 0,
        "application_evidence": 0,
        "missing_gatus": 0,
        "missing_gatus_ids": [],
        "missing_gatus_reasons": {},
        "mismatches": [],
    }
    seen_states, conflicting_direct_ids = _direct_internal_states(homelab)

    # Duplicate observations are counted once. Contradictory direct states
    # cannot be safely compared with a single Gatus observation.
    for service_id, direct_state in seen_states.items():
        if service_id in conflicting_direct_ids:
            continue
        _compare_internal_service(counters, service_id, direct_state, services.get(service_id))

    return {
        "source": "gatus_via_prometheus",
        "scope": "truenas_internal_only",
        "external_probes_preserved": True,
        "shadow_only": True,
        "state": "observed",
        "reason": "compared_observed_metrics",
        "comparable": counters["comparable"],
        "matched": counters["matched"],
        "mismatched": counters["mismatched"],
        "application_evidence": counters["application_evidence"],
        "missing_gatus": counters["missing_gatus"],
        "missing_gatus_ids": counters["missing_gatus_ids"],
        "missing_gatus_reasons": counters["missing_gatus_reasons"],
        "conflicting_direct_ids": sorted(conflicting_direct_ids),
        "mismatches": counters["mismatches"],
    }


def evaluate_internal_probe_delegation(
    platform_metrics: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Return blockers for delegating only internal generic probes to Gatus."""

    blockers: list[str] = []
    synthetic = platform_metrics.get("synthetic_probes")
    if platform_metrics.get("configured") is not True:
        blockers.append("prometheus_not_configured")
    if not isinstance(synthetic, dict) or synthetic.get("state") != "observed":
        blockers.append("gatus_not_observed")
    elif isinstance(synthetic.get("gatus_up"), bool) or not isinstance(synthetic.get("gatus_up"), (int, float)) or not _valid_gatus_up(synthetic["gatus_up"]):
        blockers.append("gatus_not_up")

    comparable = int(comparison.get("comparable") or 0)
    application_evidence = int(comparison.get("application_evidence") or 0)
    mismatched = int(comparison.get("mismatched") or 0)
    missing_gatus = int(comparison.get("missing_gatus") or 0)
    if comparable + application_evidence <= 0:
        blockers.append("no_internal_gatus_evidence")
    elif comparable == 0:
        # An HTTP application result cannot prove equivalence with a TCP probe.
        blockers.append("no_comparable_transport_evidence")
    if mismatched > 0:
        blockers.append("internal_transport_mismatches")
    if missing_gatus > 0:
        blockers.append("missing_internal_gatus_evidence")
    if comparison.get("conflicting_direct_ids"):
        blockers.append("conflicting_direct_observations")

    return {
        "provider": "gatus_via_prometheus",
        "scope": "truenas_internal_generic_only",
        "external_probe_strategy": "fastapi_cloud_embedded_outside_in",
        "external_probes_preserved": True,
        "state": "candidate" if not blockers else "blocked",
        "candidate": not blockers,
        "requires_observation_window": True,
        "blockers": blockers,
        "comparable": comparable,
        "application_evidence": application_evidence,
        "mismatched": mismatched,
        "missing_gatus": missing_gatus,
        "missing_gatus_ids": comparison.get("missing_gatus_ids", []),
        "missing_gatus_reasons": comparison.get("missing_gatus_reasons", {}),
        "conflicting_direct_ids": comparison.get("conflicting_direct_ids", []),
    }
