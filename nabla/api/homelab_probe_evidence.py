"""Short-lived rolling evidence for sampled homelab service probes."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Literal

from nabla.api.homelab_models import HomelabService

Scope = Literal["public", "internal"]
PROBE_EVIDENCE_TTL_SEC = 300.0


@dataclass(slots=True)
class _ProbeEvidence:
    row: dict[str, Any]
    observed_at: str
    recorded_at: float


_evidence: dict[Scope, dict[str, _ProbeEvidence]] = {
    "public": {},
    "internal": {},
}


def _annotated(
    entry: _ProbeEvidence,
    *,
    source: Literal["origin", "memory"],
    now: float,
    refresh_error: str | None = None,
) -> dict[str, Any]:
    age = max(0.0, now - entry.recorded_at)
    row = {
        **entry.row,
        "probe_source": source,
        "probe_observed_at": entry.observed_at,
        "probe_age_seconds": round(age, 3),
        "probe_stale": age >= PROBE_EVIDENCE_TTL_SEC,
    }
    if refresh_error:
        row["probe_refresh_error"] = refresh_error
    return row


def merge_probe_evidence(
    scope: Scope,
    *,
    current_results: list[dict[str, Any]],
    eligible_services: list[HomelabService],
    checked_at: str,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Merge one rotating sample with still-valid observations from prior cycles."""
    clock = time.monotonic() if now is None else now
    store = _evidence[scope]
    eligible_ids = {service.service_id for service in eligible_services}

    for service_id, entry in list(store.items()):
        expired = clock - entry.recorded_at >= PROBE_EVIDENCE_TTL_SEC
        if service_id not in eligible_ids or expired:
            del store[service_id]

    current_by_id = {
        str(row.get("id")): row
        for row in current_results
        if row.get("id")
    }
    merged: dict[str, dict[str, Any]] = {}

    for service_id, row in current_by_id.items():
        previous = store.get(service_id)
        if row.get("timed_out") is True and previous is not None:
            merged[service_id] = _annotated(
                previous,
                source="memory",
                now=clock,
                refresh_error=str(
                    row.get("error") or "service probe fan-out budget exceeded"
                ),
            )
            continue

        entry = _ProbeEvidence(
            row=dict(row),
            observed_at=checked_at,
            recorded_at=clock,
        )
        store[service_id] = entry
        merged[service_id] = _annotated(
            entry,
            source="origin",
            now=clock,
        )

    for service_id, entry in store.items():
        if service_id not in merged:
            merged[service_id] = _annotated(
                entry,
                source="memory",
                now=clock,
            )

    return list(merged.values())


def evidence_summary(
    results: list[dict[str, Any]],
    *,
    eligible_count: int,
) -> dict[str, Any]:
    """Describe rolling evidence coverage independently from this cycle's sample."""
    fresh = sum(row.get("probe_source") == "origin" for row in results)
    cached = sum(row.get("probe_source") == "memory" for row in results)
    known = len(results)
    return {
        "known": known,
        "fresh": fresh,
        "cached": cached,
        "coverage_percent": (
            round((known / eligible_count) * 100, 1)
            if eligible_count > 0
            else 100.0
        ),
        "evidence_ttl_seconds": PROBE_EVIDENCE_TTL_SEC,
    }


def reset_probe_evidence() -> None:
    """Clear process-local rolling evidence for deterministic tests."""
    for values in _evidence.values():
        values.clear()
