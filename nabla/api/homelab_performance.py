"""Fixed-cardinality performance telemetry for homelab health orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import TypeVar

from nabla.utils.prometheus import HOMELAB_HEALTH_PHASE_DURATION_SECONDS

_T = TypeVar("_T")

HOMELAB_HEALTH_PERF_PHASES = (
    "declared_catalog",
    "topology",
    "cloudflare_exposure",
    "pfsense_posture",
    "truenas_runtime",
    "reconciliation",
    "total",
)
_PHASE_SET = frozenset(HOMELAB_HEALTH_PERF_PHASES)
_PROVIDER_PHASES = tuple(phase for phase in HOMELAB_HEALTH_PERF_PHASES if phase != "total")


def record_homelab_phase(
    timings_ms: dict[str, float],
    phase: str,
    elapsed_seconds: float,
) -> None:
    """Record one allow-listed phase without permitting label-cardinality drift."""
    if phase not in _PHASE_SET:
        raise ValueError(f"unsupported homelab health phase: {phase}")
    elapsed = max(0.0, elapsed_seconds)
    timings_ms[phase] = round(elapsed * 1000, 1)
    HOMELAB_HEALTH_PHASE_DURATION_SECONDS.labels(phase=phase).observe(elapsed)


async def timed_homelab_phase(
    phase: str,
    awaitable: Awaitable[_T],
    timings_ms: dict[str, float],
) -> _T:
    """Time an awaitable while preserving its result and exception semantics."""
    started = time.perf_counter()
    try:
        return await awaitable
    finally:
        record_homelab_phase(timings_ms, phase, time.perf_counter() - started)


def dominant_homelab_phase(
    timings_ms: dict[str, object],
) -> tuple[str | None, float | None]:
    """Return the slowest fixed provider phase without creating dynamic labels."""
    observed: list[tuple[str, float]] = []
    for phase in _PROVIDER_PHASES:
        value = timings_ms.get(phase)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        observed.append((phase, max(0.0, float(value))))
    if not observed:
        return None, None
    return max(observed, key=lambda item: item[1])


def finalize_homelab_performance(
    payload: dict[str, object],
    *,
    total_seconds: float,
) -> dict[str, object]:
    """Attach the stable operator-facing timing contract and record total latency."""
    raw_performance = payload.get("performance")
    performance = dict(raw_performance) if isinstance(raw_performance, dict) else {}
    raw_timings = performance.get("phases_ms")
    timings = dict(raw_timings) if isinstance(raw_timings, dict) else {}
    record_homelab_phase(timings, "total", total_seconds)
    normalized_timings = {phase: timings.get(phase) for phase in HOMELAB_HEALTH_PERF_PHASES}
    dominant_phase, dominant_phase_ms = dominant_homelab_phase(normalized_timings)
    performance["phases_ms"] = normalized_timings
    performance["dominant_phase"] = dominant_phase
    performance["dominant_phase_ms"] = dominant_phase_ms
    performance["fixed_cardinality"] = True
    performance["phase_count"] = len(HOMELAB_HEALTH_PERF_PHASES)
    return {**payload, "performance": performance}


__all__ = [
    "HOMELAB_HEALTH_PERF_PHASES",
    "dominant_homelab_phase",
    "finalize_homelab_performance",
    "record_homelab_phase",
    "timed_homelab_phase",
]
