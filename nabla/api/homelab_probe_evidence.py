"""Short-lived rolling evidence for sampled homelab service probes."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Literal

from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_policy import (
    HEALTH_CACHE_TTL_SEC,
    MAX_INTERNAL_PROBES_PER_REFRESH,
    MAX_PUBLIC_PROBES_PER_REFRESH,
    estimated_probe_interval_seconds,
)

Scope = Literal["public", "internal"]
PROBE_EVIDENCE_TTL_SEC = 300.0
MAX_PROBE_EVIDENCE_RETENTION_SEC = 3600.0


@dataclass(slots=True)
class _ProbeEvidence:
    row: dict[str, Any]
    observed_at: str
    recorded_at: float
    interval_seconds: float | None


_evidence: dict[Scope, dict[str, _ProbeEvidence]] = {
    "public": {},
    "internal": {},
}


def _stale_after_seconds(entry: _ProbeEvidence) -> float:
    cadence = entry.interval_seconds or PROBE_EVIDENCE_TTL_SEC
    return max(HEALTH_CACHE_TTL_SEC * 2, cadence * 2)


def _retention_seconds(entry: _ProbeEvidence) -> float:
    cadence = entry.interval_seconds or PROBE_EVIDENCE_TTL_SEC
    return max(PROBE_EVIDENCE_TTL_SEC, min(MAX_PROBE_EVIDENCE_RETENTION_SEC, cadence * 3))


def _annotated(
    entry: _ProbeEvidence,
    *,
    source: Literal["origin", "memory", "deadline"],
    now: float,
    refresh_error: str | None = None,
) -> dict[str, Any]:
    age = max(0.0, now - entry.recorded_at)
    stale_after = _stale_after_seconds(entry)
    row = {
        **entry.row,
        "probe_source": source,
        "probe_observed_at": entry.observed_at,
        "probe_age_seconds": round(age, 3),
        "probe_stale": age >= stale_after,
        "probe_stale_after_seconds": round(stale_after, 3),
    }
    if entry.interval_seconds is not None:
        row["probe_interval_seconds"] = round(entry.interval_seconds, 3)
        row["next_probe_in_seconds"] = round(max(0.0, entry.interval_seconds - age), 3)
    if refresh_error:
        row["probe_refresh_error"] = refresh_error
    return row


def _cadence_by_service(
    scope: Scope,
    eligible_services: list[HomelabService],
) -> dict[str, float | None]:
    limit = MAX_PUBLIC_PROBES_PER_REFRESH if scope == "public" else MAX_INTERNAL_PROBES_PER_REFRESH
    return {
        service.service_id: estimated_probe_interval_seconds(
            service,
            eligible_services=eligible_services,
            limit=limit,
        )
        for service in eligible_services
    }


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
    cadence_by_id = _cadence_by_service(scope, eligible_services)

    for service_id, entry in list(store.items()):
        entry.interval_seconds = cadence_by_id.get(service_id)
        expired = clock - entry.recorded_at >= _retention_seconds(entry)
        if service_id not in eligible_ids or expired:
            del store[service_id]

    current_by_id = {str(row.get("id")): row for row in current_results if row.get("id")}
    merged: dict[str, dict[str, Any]] = {}

    for service_id, row in current_by_id.items():
        previous = store.get(service_id)
        if row.get("timed_out") is True:
            if previous is not None:
                merged[service_id] = _annotated(
                    previous,
                    source="memory",
                    now=clock,
                    refresh_error=str(row.get("error") or "service probe fan-out budget exceeded"),
                )
            else:
                transient = _ProbeEvidence(
                    row=dict(row),
                    observed_at=checked_at,
                    recorded_at=clock,
                    interval_seconds=cadence_by_id.get(service_id),
                )
                merged[service_id] = _annotated(transient, source="deadline", now=clock)
            continue

        entry = _ProbeEvidence(
            row=dict(row),
            observed_at=checked_at,
            recorded_at=clock,
            interval_seconds=cadence_by_id.get(service_id),
        )
        store[service_id] = entry
        merged[service_id] = _annotated(entry, source="origin", now=clock)

    for service_id, entry in store.items():
        if service_id not in merged:
            merged[service_id] = _annotated(entry, source="memory", now=clock)

    return list(merged.values())


def evidence_summary(
    results: list[dict[str, Any]],
    *,
    eligible_count: int,
) -> dict[str, Any]:
    """Describe rolling evidence coverage independently from this cycle's sample."""
    fresh = sum(row.get("probe_source") == "origin" for row in results)
    cached = sum(row.get("probe_source") == "memory" for row in results)
    known = fresh + cached
    return {
        "known": known,
        "fresh": fresh,
        "cached": cached,
        "coverage_percent": (round((known / eligible_count) * 100, 1) if eligible_count > 0 else 100.0),
        "evidence_ttl_seconds": PROBE_EVIDENCE_TTL_SEC,
        "evidence_max_retention_seconds": MAX_PROBE_EVIDENCE_RETENTION_SEC,
    }


def reset_probe_evidence() -> None:
    """Clear process-local rolling evidence for deterministic tests."""
    for values in _evidence.values():
        values.clear()
