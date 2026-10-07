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
