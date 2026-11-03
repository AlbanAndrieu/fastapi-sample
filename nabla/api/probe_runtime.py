"""Rolling probe warm-up summary exposed by ``/api/homelab/probes``."""

from __future__ import annotations

import math
import time
from typing import Any

from nabla.api.platform_health_diagnostics import utc_now

_PROBE_RUNTIME_STARTED_AT = utc_now()
_PROBE_RUNTIME_STARTED_MONOTONIC = time.monotonic()


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _probe_scope_progress(summary: dict[str, Any], scope: str) -> tuple[int, int]:
    scope_summary = summary.get(scope)
    if not isinstance(scope_summary, dict):
        return 0, 0
    if scope_summary.get("enabled") is False:
        return 0, 0
    evidence = scope_summary.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    return (
        _nonnegative_int(scope_summary.get("eligible")),
        _nonnegative_int(evidence.get("known")),
    )


def _probe_cadence_values(payload: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for field in ("public_probe_results", "internal_services"):
        rows = payload.get(field)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            interval = row.get("probe_interval_seconds")
            if isinstance(interval, bool) or not isinstance(interval, (int, float)):
                continue
            if interval > 0 and math.isfinite(interval):
                values.append(float(interval))
    return values


def _eligible_cycle_estimate(summary: dict[str, Any]) -> float | None:
    """Use every enabled eligible scope; do not infer unseen cadence from rows."""
    estimates: list[float] = []
    for scope in ("public", "internal"):
        data = summary.get(scope)
        if not isinstance(data, dict) or data.get("enabled") is False:
            continue
        if _nonnegative_int(data.get("eligible")) == 0:
            continue
        value = data.get("estimated_full_cycle_seconds")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            return None
        estimates.append(float(value))
    return max(estimates) if estimates else None


def probe_runtime_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize rolling probe warm-up without scheduling any additional work."""
    summary = payload.get("probe_summary")
    summary = summary if isinstance(summary, dict) else {}
    public_eligible, public_known = _probe_scope_progress(summary, "public")
    internal_eligible, internal_known = _probe_scope_progress(summary, "internal")
    eligible = public_eligible + internal_eligible
    known = min(eligible, public_known + internal_known)
    coverage = 100.0 if eligible == 0 else round((known / eligible) * 100, 1)
    cadence_values = _probe_cadence_values(payload)
    candidate_estimate = _eligible_cycle_estimate(summary)
    observed_estimate = max(cadence_values) if cadence_values else None

    return {
        "started_at": _PROBE_RUNTIME_STARTED_AT,
        "uptime_seconds": round(
            max(0.0, time.monotonic() - _PROBE_RUNTIME_STARTED_MONOTONIC),
            3,
        ),
        "state": "ready" if known >= eligible else "warming",
        "eligible_probe_slots": eligible,
        "known_probe_slots": known,
        "coverage_percent": coverage,
        "estimated_full_cycle_seconds": (
            round(candidate_estimate, 3)
            if candidate_estimate is not None
            else round(observed_estimate, 3)
            if observed_estimate is not None
            else None
        ),
        "estimate_source": (
            "eligible_catalog"
            if candidate_estimate is not None
            else "observed_rows"
            if observed_estimate is not None
            else "unavailable"
        ),
        "refresh_model": "on_request",
        "evidence_storage": "process_memory",
    }
