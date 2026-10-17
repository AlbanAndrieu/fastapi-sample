#!/usr/bin/env python3
"""Summarize existing health-board JSON lines without making network requests.

Input: one compact /api/health-board JSON object per line (stdin).
Output: one whitelisted, credential-free diagnostic object per line.
"""

from __future__ import annotations

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
    evidence = _object(scope.get("evidence"))
    return {
        "completed": _bounded_number(scope.get("completed")),
        "timed_out": _bounded_number(scope.get("timed_out")),
        "priority_source": _allowed_text(
            scope.get("priority_source"), {"bootstrap", "catalog"}
        ),
        "coverage_percent": _bounded_number(evidence.get("coverage_percent")),
        "timing": {
            key: _bounded_number(timing.get(key)) for key in _TIMING_FIELDS
        },
    }


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Conservatively label cache and exposure evidence, without raw payloads."""
    board = _object(snapshot)
    homelab = _object(board.get("homelab", board))
    summary = _object(homelab.get("probe_summary"))
    cache = _object(homelab.get("probe_cache"))
    state = _allowed_text(board.get("state"), {"fresh", "stale", "pending"})
    internal_ids = {
        row["id"]
        for row in homelab.get("internal_services", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row["id"] in _GARAGE_IDS
    }
    garage_rows = {
        row["id"]: row
        for row in homelab.get("services", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row["id"] in _GARAGE_IDS
    }
    garage: dict[str, dict[str, Any]] = {}
    for service_id in sorted(_GARAGE_IDS):
        row = garage_rows.get(service_id, {})
        garage[service_id] = {
            "lan_observed": service_id in internal_ids,
            "internal_state": _allowed_text(
                row.get("internal_state"), {"ok", "warn", "fail"}
            ),
            "exposure_intent": _allowed_text(
                row.get("exposure_intent"), {"internal", "public"}
            ),
            "unexpected_tunnel_route": (
                row.get("unexpected_tunnel_route")
                if type(row.get("unexpected_tunnel_route")) is bool
                else None
            ),
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
            cache.get("source"), {"origin", "memory"}
        ),
        "probe_cache_age_seconds": _bounded_number(cache.get("age_seconds")),
        "public": public,
        "internal": internal,
        "garage": garage,
        "warnings": warnings,
    }


def main() -> int:
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
        print(json.dumps(summarize(snapshot), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
