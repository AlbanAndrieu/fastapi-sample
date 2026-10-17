#!/usr/bin/env python3
"""Summarize existing health-board JSON lines without making network requests.

Input: one compact /api/health-board JSON object per line (stdin).
Output: one whitelisted, credential-free diagnostic object per line.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

_MAX_LINE_BYTES = 2_000_000
_GARAGE_IDS = frozenset({"garage", "garage-admin", "garage-webui"})
_TIMING_FIELDS = (
    "completed_samples",
    "max_queue_wait_ms",
    "max_dns_probe_ms",
    "max_http_request_ms",
    "max_access_secondary_ms",
)
_DEADLINE_PHASES = (
    "not_started",
    "waiting_on_semaphore",
    "dns_in_progress",
    "head_get_in_progress",
    "access_secondary_in_progress",
    "tcp_in_progress",
)


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _allowed_text(value: Any, allowed: set[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _bounded_number(value: Any) -> int | float | None:
    if type(value) not in (int, float):
        return None
    if not 0 <= value <= 1_000_000:
        return None
    return value


def _summary(scope: dict[str, Any]) -> dict[str, Any]:
    timing = _object(scope.get("timing"))
    phases = _object(scope.get("deadline_phase_counts"))
    evidence = _object(scope.get("evidence"))
    return {
        "completed": _bounded_number(scope.get("completed")),
        "timed_out": _bounded_number(scope.get("timed_out")),
        "priority_source": _allowed_text(
            scope.get("priority_source"),
            {"bootstrap", "catalog"},
        ),
        "coverage_percent": _bounded_number(evidence.get("coverage_percent")),
        "timing": {key: _bounded_number(timing.get(key)) for key in _TIMING_FIELDS},
        "deadline_phase_counts": {key: _bounded_number(phases.get(key)) for key in _DEADLINE_PHASES},
    }


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Conservatively label cache and exposure evidence, without raw payloads."""
    board = _object(snapshot)
    homelab = _object(board.get("homelab", board))
    summary = _object(homelab.get("probe_summary"))
    cache = _object(homelab.get("probe_cache"))
    state = _allowed_text(board.get("state"), {"fresh", "stale", "pending"})
    internal_ids = {row["id"] for row in homelab.get("internal_services", []) if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] in _GARAGE_IDS}
    garage_rows = {row["id"]: row for row in homelab.get("services", []) if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] in _GARAGE_IDS}
    garage: dict[str, dict[str, Any]] = {}
    for service_id in sorted(_GARAGE_IDS):
        row = garage_rows.get(service_id, {})
        garage[service_id] = {
            "lan_observed": service_id in internal_ids,
            "internal_state": _allowed_text(
                row.get("internal_state"),
                {"ok", "warn", "fail"},
            ),
            "exposure_intent": _allowed_text(
                row.get("exposure_intent"),
                {"internal", "public"},
            ),
            "unexpected_tunnel_route": (row.get("unexpected_tunnel_route") if type(row.get("unexpected_tunnel_route")) is bool else None),
        }
    public = _summary(_object(summary.get("public")))
    internal = _summary(_object(summary.get("internal")))
    warnings = []
    if state in {"pending", "stale"} or cache.get("stale") is True:
        warnings.append("cached_or_pending_evidence_not_fresh")
    if public["timed_out"]:
        warnings.append("public_fanout_deadline_not_service_down")
    if garage["garage-admin"]["unexpected_tunnel_route"] is True:
        warnings.append("garage_admin_exposure_drift")
    return {
        "board_state": state,
        "board_age_seconds": _bounded_number(board.get("age_seconds")),
        "probe_cache_source": _allowed_text(
            cache.get("source"),
            {"origin", "memory"},
        ),
        "probe_cache_age_seconds": _bounded_number(cache.get("age_seconds")),
        "public": public,
        "internal": internal,
        "garage": garage,
        "warnings": warnings,
    }


_MAX_AGGREGATE_SNAPSHOTS = 64


def _aggregate_range(values: list[int | float]) -> dict[str, int | float | None]:
    return {
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def aggregate_cycles(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare bounded observed waves without counting cached snapshots as fresh."""
    # A fresh health-board envelope may still contain a retained homelab wave.
    # Only origin-sourced cycles can attribute current scheduler results.
    origin = [cycle for cycle in cycles if cycle["board_state"] == "fresh" and cycle["probe_cache_source"] == "origin"]
    public_completed = [value for cycle in origin if isinstance(value := cycle["public"]["completed"], (int, float))]
    public_deadlines = [value for cycle in origin if isinstance(value := cycle["public"]["timed_out"], (int, float))]
    phase_maxima = {
        field: max(
            [value for cycle in origin if isinstance(value := cycle["public"]["timing"].get(field), (int, float))],
            default=None,
        )
        for field in _TIMING_FIELDS[1:]
    }
    garage_lan = [all(cycle["garage"][key]["lan_observed"] and cycle["garage"][key]["internal_state"] == "ok" for key in _GARAGE_IDS) for cycle in origin]
    pending_phase_totals = {
        phase: sum(cycle["public"]["deadline_phase_counts"].get(phase) or 0 for cycle in origin)
        for phase in _DEADLINE_PHASES
    }
    return {
        "total_snapshots": len(cycles),
        "fresh_envelopes": sum(cycle["board_state"] == "fresh" for cycle in cycles),
        "stale_or_pending_envelopes": sum(cycle["board_state"] in {"stale", "pending"} for cycle in cycles),
        "origin_cycles": len(origin),
        "public_completed_range": _aggregate_range(public_completed),
        "public_deadline_range": _aggregate_range(public_deadlines),
        "origin_cycles_with_public_deadlines": sum(value > 0 for value in public_deadlines),
        "observed_phase_maxima_ms": phase_maxima,
        "deadline_phase_totals": pending_phase_totals,
        "all_three_garage_lan_ok_origin_cycles": sum(garage_lan),
        "garage_admin_unexpected_route_seen": any(cycle["garage"]["garage-admin"]["unexpected_tunnel_route"] is True for cycle in origin),
        "interpretation": (
            "insufficient_current_origin_evidence"
            if not origin
            else "variable_public_completion"
            if len(public_completed) >= 2 and min(public_completed) != max(public_completed)
            else "current_origin_samples_not_independent_outside_in_proof"
        ),
        "limits": "Completed-probe maxima exclude cancelled tasks; deadline phases are last observed checkpoints, not completed operations. Origin cycles are not independent WAN tests.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="summarize up to 64 existing snapshots as one redacted comparison",
    )
    args = parser.parse_args()
    collected: list[dict[str, Any]] = []
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
            print(f"line {line_number}: JSON input too large", file=sys.stderr)
            return 2
        try:
            snapshot = json.loads(line)
        except json.JSONDecodeError:
            print(f"line {line_number}: invalid JSON", file=sys.stderr)
            return 2
        if not isinstance(snapshot, dict):
            print(f"line {line_number}: expected JSON object", file=sys.stderr)
            return 2
        summary = summarize(snapshot)
        if args.aggregate:
            if len(collected) >= _MAX_AGGREGATE_SNAPSHOTS:
                print("too many input snapshots for aggregate mode", file=sys.stderr)
                return 2
            collected.append(summary)
        else:
            print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    if args.aggregate:
        print(json.dumps(aggregate_cycles(collected), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
