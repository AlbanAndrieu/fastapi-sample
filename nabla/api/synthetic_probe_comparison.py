"""Shadow-only comparison between direct homelab probes and Gatus evidence."""

from __future__ import annotations

from typing import Any

_SCOPE_TYPES = {
    "public": ("HTTP", "HTTPS"),
    "internal": ("TCP",),
}


def _matching_gatus_probe(
    service: dict[str, Any],
    probe_types: tuple[str, ...],
) -> tuple[str, float] | None:
    for probe_type in probe_types:
        evidence = service.get(probe_type)
        if not isinstance(evidence, dict):
            continue
        value = evidence.get("success")
        if isinstance(value, (int, float)):
            return probe_type, float(value)
    return None


def compare_synthetic_probe_evidence(
    homelab: dict[str, Any],
    platform_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Compare equivalent direct/Gatus probes without changing health verdicts."""

    synthetic = platform_metrics.get("synthetic_probes")
    services = synthetic.get("services") if isinstance(synthetic, dict) else None
    if not isinstance(services, dict):
        return {
            "source": "gatus_via_prometheus",
            "shadow_only": True,
            "state": "unavailable",
            "comparable": 0,
            "matched": 0,
            "mismatched": 0,
            "missing_gatus": 0,
            "mismatches": [],
        }

    comparable = 0
    matched = 0
    mismatched = 0
    missing_gatus = 0
    mismatches: list[dict[str, Any]] = []

    for scope, field in (
        ("public", "public_probe_results"),
        ("internal", "internal_services"),
    ):
        rows = homelab.get(field)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            service_id = str(row.get("id") or "").strip()
            direct_state = str(row.get("state") or "").strip().lower()
            if not service_id or direct_state not in {"ok", "fail"}:
                continue
            synthetic_service = services.get(service_id)
            if not isinstance(synthetic_service, dict):
                missing_gatus += 1
                continue
            gatus = _matching_gatus_probe(
                synthetic_service,
                _SCOPE_TYPES[scope],
            )
            if gatus is None:
                missing_gatus += 1
                continue
            probe_type, success = gatus
            comparable += 1
            direct_up = direct_state == "ok"
            gatus_up = success >= 1.0
            if direct_up == gatus_up:
                matched += 1
                continue
            mismatched += 1
            mismatches.append(
                {
                    "id": service_id,
                    "scope": scope,
                    "direct_state": direct_state,
                    "gatus_type": probe_type,
                    "gatus_success": success,
                }
            )

    return {
        "source": "gatus_via_prometheus",
        "shadow_only": True,
        "state": "observed",
        "comparable": comparable,
        "matched": matched,
        "mismatched": mismatched,
        "missing_gatus": missing_gatus,
        "mismatches": mismatches,
    }


def evaluate_generic_probe_cutover(
    platform_metrics: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Return explicit blockers for replacing direct generic probes with Gatus."""

    blockers: list[str] = []
    synthetic = platform_metrics.get("synthetic_probes")
    if platform_metrics.get("configured") is not True:
        blockers.append("prometheus_not_configured")
    if not isinstance(synthetic, dict) or synthetic.get("state") != "observed":
        blockers.append("gatus_not_observed")
    elif not isinstance(synthetic.get("gatus_up"), (int, float)) or float(
        synthetic["gatus_up"]
    ) < 1.0:
        blockers.append("gatus_not_up")

    comparable = int(comparison.get("comparable") or 0)
    mismatched = int(comparison.get("mismatched") or 0)
    missing_gatus = int(comparison.get("missing_gatus") or 0)
    if comparable <= 0:
        blockers.append("no_comparable_probes")
    if mismatched > 0:
        blockers.append("shadow_mismatches")
    if missing_gatus > 0:
        blockers.append("missing_gatus_evidence")

    return {
        "provider": "gatus_via_prometheus",
        "state": "candidate" if not blockers else "blocked",
        "candidate": not blockers,
        "requires_observation_window": True,
        "blockers": blockers,
        "comparable": comparable,
        "mismatched": mismatched,
        "missing_gatus": missing_gatus,
    }
