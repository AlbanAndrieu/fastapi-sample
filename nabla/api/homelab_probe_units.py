"""Pure, offline deployment-unit planning for a future catalog-v2 probe runtime.

This module never performs I/O or starts probes. Missing unit metadata leaves
endpoints independent; do not infer operational grouping from similar names.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

Observer = Literal["internal", "public"]


@dataclass(frozen=True)
class ProbeUnit:
    """A deployment selection, not an unlimited endpoint-probe allowance."""

    unit_id: str
    component_ids: tuple[str, ...]
    priority: int | None
    primary_endpoint: str | None
    secondary_endpoints: tuple[str, ...]


def _optional_rank(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 1000:
        raise ValueError(f"{field} must be an integer between 0 and 1000")
    return value


def build_probe_units(
    records: Sequence[Mapping[str, Any]], *, observer: Observer
) -> list[ProbeUnit]:
    """Build explicit units, retaining component IDs and strict exposure intent.

    The public observer cannot probe a private component. A partially public
    deployment unit retains only its eligible endpoints for that observer.
    """
    if observer not in ("internal", "public"):
        raise ValueError("observer must be 'internal' or 'public'")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    seen: set[str] = set()
    for record in records:
        component_id = record.get("id", record.get("serviceId"))
        if not isinstance(component_id, str) or not component_id:
            raise ValueError("Every component needs a nonempty id")
        if component_id in seen:
            raise ValueError(f"Duplicate component id: {component_id}")
        seen.add(component_id)
        external = record.get("external", False)
        if type(external) is not bool:
            raise ValueError(f"external must be boolean for {component_id}")
        unit_id = record.get("deploymentUnitId")
        if unit_id is not None and (
            not isinstance(unit_id, str) or not unit_id.strip()
        ):
            raise ValueError(f"Invalid deploymentUnitId for {component_id}")
        _optional_rank(record.get("probePriority"), "probePriority")
        if observer == "public" and not external:
            continue
        # Never group undeclared units by hostname or ID prefix.
        key = unit_id or f"service:{component_id}"
        grouped.setdefault(key, []).append(record)

    units = []
    for unit_id, members in grouped.items():
        ids = tuple(
            str(member.get("id", member.get("serviceId"))) for member in members
        )
        ranks = [
            _optional_rank(member.get("probePriority"), "probePriority")
            for member in members
        ]
        assigned = [rank for rank in ranks if rank is not None]
        rank = min(assigned) if assigned else None
        policies = [
            member["probePolicy"]
            for member in members
            if member.get("probePolicy") is not None
        ]
        if policies and any(policy != policies[0] for policy in policies[1:]):
            raise ValueError(f"Conflicting probePolicy in unit {unit_id}")
        primary: str | None = None
        secondary: tuple[str, ...] = ()
        if policies:
            policy = policies[0]
            if not isinstance(policy, dict):
                raise ValueError(f"probePolicy must be an object in {unit_id}")
            primary = policy.get("primaryEndpoint")
            secondaries = policy.get("secondaryEndpoints", [])
            if not isinstance(primary, str) or not primary:
                raise ValueError(f"primaryEndpoint is required in {unit_id}")
            if not isinstance(secondaries, list) or any(
                not isinstance(item, str) or not item for item in secondaries
            ):
                raise ValueError(f"secondaryEndpoints must be string IDs in {unit_id}")
            if len(set([primary, *secondaries])) != len(secondaries) + 1:
                raise ValueError(f"Duplicate endpoint in probePolicy for {unit_id}")
            # In a split public/private unit, retain only eligible endpoints.
            if primary not in ids:
                if observer == "internal":
                    raise ValueError(f"Unknown primaryEndpoint in unit {unit_id}")
                primary = None
            unknown = [name for name in secondaries if name not in ids]
            if observer == "internal" and unknown:
                raise ValueError(f"Unknown secondaryEndpoint in unit {unit_id}")
            secondary = tuple(name for name in secondaries if name in ids)
        else:
            # Safe bootstrap: a single endpoint, no implicit admin fan-out.
            primary = ids[0]
        units.append(
            ProbeUnit(
                unit_id=unit_id,
                component_ids=ids,
                priority=rank,
                primary_endpoint=primary,
                secondary_endpoints=secondary,
            )
        )
    return sorted(units, key=lambda item: item.unit_id)


def select_probe_units(
    units: Sequence[ProbeUnit], *, limit: int, cycle: int
) -> list[ProbeUnit]:
    """Select a bounded mix of ranked units and fair rotating units.

    With a full 12-unit cycle reserve two rotating slots. Tiny saturated
    budgets reserve one slot (including limit=1) to avoid permanent starvation.
    """
    if limit <= 0:
        return []
    if cycle < 0:
        raise ValueError("cycle must be non-negative")
    unique: dict[str, ProbeUnit] = {}
    for unit in units:
        if unit.unit_id in unique:
            raise ValueError(f"Duplicate unit id: {unit.unit_id}")
        unique[unit.unit_id] = unit
    if len(unique) <= limit:
        return list(unique.values())
    ranked = sorted(
        (unit for unit in unique.values() if unit.priority is not None),
        key=lambda unit: (unit.priority, unit.unit_id),
    )
    reserved = min(2, limit - 3) if limit > 3 else 1
    fixed = ranked[: max(0, limit - reserved)]
    fixed_ids = {unit.unit_id for unit in fixed}
    rotating = sorted(
        (unit for unit in unique.values() if unit.unit_id not in fixed_ids),
        key=lambda unit: (
            unit.priority is None,
            unit.priority if unit.priority is not None else 1001,
            unit.unit_id,
        ),
    )
    slots = limit - len(fixed)
    start = (cycle * slots) % len(rotating)
    return [
        *fixed,
        *(rotating[(start + offset) % len(rotating)] for offset in range(slots)),
    ]


def main() -> int:
    """Preview unit selections from a local catalog; never execute the probes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--observer", choices=("internal", "public"), required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--cycle", type=int, default=0)
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    records = payload.get("services") if isinstance(payload, dict) else payload
    if not isinstance(records, list) or any(
        not isinstance(item, dict) for item in records
    ):
        parser.error("catalog must contain a services array")
    units = build_probe_units(records, observer=args.observer)
    selected = select_probe_units(units, limit=args.limit, cycle=args.cycle)
    output = {
        "observer": args.observer,
        "unit_budget": args.limit,
        "eligible_units": len(units),
        "selected_units": [
            {
                "unit_id": unit.unit_id,
                "component_ids": unit.component_ids,
                "primary_endpoint": unit.primary_endpoint,
                "conditional_secondary_endpoints": unit.secondary_endpoints,
            }
            for unit in selected
        ],
        "execution_performed": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
