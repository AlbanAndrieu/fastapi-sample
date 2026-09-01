"""Propagate required topology dependency health across homelab service rows."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from nabla.api.homelab_topology import (
    HomelabRelationStrength,
    HomelabRelationType,
    HomelabTopology,
    HomelabTopologyRelation,
)

HealthState = str

_HEALTH_STATES = frozenset({"ok", "warn", "fail", "unknown"})
_HEALTH_BEARING_RELATION_TYPES = frozenset(
    {
        HomelabRelationType.DEPENDS_ON,
        HomelabRelationType.CONSUMES_API,
        HomelabRelationType.ROUTES_TO,
        HomelabRelationType.STORES_IN,
        HomelabRelationType.AUTHENTICATES_VIA,
        HomelabRelationType.EXPOSED_BY,
    }
)


def _health_state(value: object) -> HealthState:
    state = str(value or "unknown").strip().lower()
    return state if state in _HEALTH_STATES else "unknown"


def _dependency_state(states: list[HealthState]) -> HealthState | None:
    """Aggregate required target states without hiding uncertainty."""
    if not states:
        return None
    if "fail" in states:
        return "fail"
    if "warn" in states:
        return "warn"
    if "unknown" in states:
        return "unknown"
    return "ok"


def _effective_state(
    local_state: HealthState,
    dependency_state: HealthState | None,
) -> HealthState:
    """Keep direct failures red and dependency failures visibly degraded."""
    if local_state == "fail":
        return "fail"
    if dependency_state in {"fail", "warn", "unknown"}:
        return "warn"
    return local_state


def _required_relations(
    topology: HomelabTopology,
) -> dict[str, list[HomelabTopologyRelation]]:
    required: dict[str, list[HomelabTopologyRelation]] = defaultdict(list)
    for relation in topology.relations:
        if relation.strength != HomelabRelationStrength.REQUIRED:
            continue
        if relation.type not in _HEALTH_BEARING_RELATION_TYPES:
            continue
        required[relation.source].append(relation)
    return dict(required)


def _reachable(start: str, graph: dict[str, set[str]]) -> set[str]:
    """Return nodes reachable from ``start`` without recursive traversal."""
    seen: set[str] = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(graph.get(node, set()) - seen)
    return seen


def _required_dependency_cycles(
    required: dict[str, list[HomelabTopologyRelation]],
) -> dict[str, list[str]]:
    """Map nodes in required-edge strongly connected components to cycle members."""
    nodes = set(required)
    for relations in required.values():
        nodes.update(relation.target for relation in relations)

    graph = {node: set() for node in nodes}
    reverse = {node: set() for node in nodes}
    for source, relations in required.items():
        for relation in relations:
            graph[source].add(relation.target)
            reverse[relation.target].add(source)

    cycles: dict[str, list[str]] = {}
    remaining = set(nodes)
    while remaining:
        start = min(remaining)
        component = _reachable(start, graph) & _reachable(start, reverse)
        remaining.difference_update(component)
        if len(component) <= 1:
            continue
        members = sorted(component)
        for member in component:
            cycles[member] = members
    return cycles


def _dependency_target_state(
    target: str,
    *,
    effective_states: dict[str, HealthState],
    rows_by_id: dict[str, dict[str, Any]],
) -> HealthState:
    """Treat stale non-failing evidence as unknown for required dependencies."""
    state = effective_states.get(target, "unknown")
    target_row = rows_by_id.get(target)
    if state != "fail" and target_row is not None and target_row.get("observation_stale"):
        return "unknown"
    return state


def _dependency_evidence(
    relation: HomelabTopologyRelation,
    *,
    target_state: HealthState,
    target_effective_state: HealthState,
    target_row: dict[str, Any] | None,
    node_names: dict[str, str],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "target": relation.target,
        "target_name": node_names.get(relation.target, relation.target),
        "relation_type": relation.type.value,
        "target_state": target_state,
        "target_effective_state": target_effective_state,
        "evidence": list(relation.evidence),
    }
    if target_row is not None:
        freshness_fields = {
            "observed_at": "target_observed_at",
            "observation_age_seconds": "target_observation_age_seconds",
            "observation_stale": "target_observation_stale",
        }
        for source_key, evidence_key in freshness_fields.items():
            if source_key in target_row:
                evidence[evidence_key] = target_row[source_key]
    if relation.description:
        evidence["description"] = relation.description
    return evidence


def propagate_required_dependency_health(
    rows: list[dict[str, Any]],
    topology: HomelabTopology,
) -> list[dict[str, Any]]:
    """Add local/dependency/effective states using required topology relations.

    ``state`` remains the backwards-compatible final state. New clients can use
    ``local_state`` to preserve the service's own HTTP/runtime outcome and
    ``effective_state`` for the dependency-aware result.
    """
    enriched = [dict(row) for row in rows]
    rows_by_id = {
        str(row.get("id")): row
        for row in enriched
        if isinstance(row.get("id"), str) and row.get("id")
    }
    required = _required_relations(topology)
    cycles = _required_dependency_cycles(required)
    node_names = {node.id: node.name for node in topology.nodes}
    local_states = {
        service_id: _health_state(row.get("state"))
        for service_id, row in rows_by_id.items()
    }
    effective_states = dict(local_states)

    # Resolve dependency chains to a fixed point. Required cycles are handled by
    # bounded iteration and surfaced separately through ``dependency_cycle``.
    for _ in range(max(1, len(rows_by_id) + 1)):
        changed = False
        next_states = dict(effective_states)
        for service_id, local_state in local_states.items():
            relations = required.get(service_id, [])
            target_states = [
                _dependency_target_state(
                    relation.target,
                    effective_states=effective_states,
                    rows_by_id=rows_by_id,
                )
                for relation in relations
            ]
            resolved = _effective_state(
                local_state,
                _dependency_state(target_states),
            )
            if resolved != effective_states.get(service_id):
                next_states[service_id] = resolved
                changed = True
        effective_states = next_states
        if not changed:
            break

    result: list[dict[str, Any]] = []
    for row in enriched:
        service_id = str(row.get("id") or "")
        local_state = _health_state(row.get("state"))
        relations = required.get(service_id, [])
        target_effective_states = [
            effective_states.get(relation.target, "unknown") for relation in relations
        ]
        target_states = [
            _dependency_target_state(
                relation.target,
                effective_states=effective_states,
                rows_by_id=rows_by_id,
            )
            for relation in relations
        ]
        dependency_state = _dependency_state(target_states)
        effective_state = effective_states.get(
            service_id,
            _effective_state(local_state, dependency_state),
        )
        blocked_by = [
            relation.target
            for relation, target_state in zip(relations, target_states, strict=True)
            if target_state != "ok"
        ]

        row.update(
            {
                "state": effective_state,
                "local_state": local_state,
                "dependency_state": dependency_state,
                "effective_state": effective_state,
                "required_dependencies": [relation.target for relation in relations],
                "blocked_by": blocked_by,
                "dependency_cycle": cycles.get(service_id, []),
                "dependency_evidence": [
                    _dependency_evidence(
                        relation,
                        target_state=target_state,
                        target_effective_state=target_effective_state,
                        target_row=rows_by_id.get(relation.target),
                        node_names=node_names,
                    )
                    for relation, target_state, target_effective_state in zip(
                        relations,
                        target_states,
                        target_effective_states,
                        strict=True,
                    )
                ],
            }
        )
        result.append(row)

    return result
