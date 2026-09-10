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
    },
)


def _health_state(value: object) -> HealthState:
    state = str(value or "unknown").strip().lower()
    return state if state in _HEALTH_STATES else "unknown"


def _dependency_state(states: list[HealthState]) -> HealthState | None:
    if not states:
        return None
    if "fail" in states:
        return "fail"
    if "warn" in states:
        return "warn"
    if "unknown" in states:
        return "unknown"
    return "ok"


def _effective_state(local_state: HealthState, dependency_state: HealthState | None) -> HealthState:
    """Do not turn missing/stale dependency evidence into a service incident."""
    if local_state == "fail":
        return "fail"
    if dependency_state in {"fail", "warn"}:
        return "warn"
    return local_state


def _required_relations(topology: HomelabTopology) -> dict[str, list[HomelabTopologyRelation]]:
    required: dict[str, list[HomelabTopologyRelation]] = defaultdict(list)
    for relation in topology.relations:
        if relation.strength != HomelabRelationStrength.REQUIRED:
            continue
        if relation.type in _HEALTH_BEARING_RELATION_TYPES:
            required[relation.source].append(relation)
    return dict(required)


def _reachable(start: str, graph: dict[str, set[str]]) -> set[str]:
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
        if len(component) > 1:
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
    target_row = rows_by_id.get(target)
    if target_row is None:
        return "unknown"
    if target_row.get("observation_stale") or target_row.get("runtime_stale"):
        return "unknown"
    return effective_states.get(target, "unknown")


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
        for source_key, evidence_key in (
            ("observed_at", "target_observed_at"),
            ("observation_age_seconds", "target_observation_age_seconds"),
            ("observation_stale", "target_observation_stale"),
        ):
            if source_key in target_row:
                evidence[evidence_key] = target_row[source_key]
    if relation.description:
        evidence["description"] = relation.description
    return evidence


def propagate_required_dependency_health(
    rows: list[dict[str, Any]],
    topology: HomelabTopology,
) -> list[dict[str, Any]]:
    """Propagate confirmed failures while surfacing unknown dependencies separately."""
    enriched = [dict(row) for row in rows]
    rows_by_id = {str(row["id"]): row for row in enriched if isinstance(row.get("id"), str) and row.get("id")}
    required = _required_relations(topology)
    cycles = _required_dependency_cycles(required)
    node_names = {node.id: node.name for node in topology.nodes}
    local_states = {service_id: _health_state(row.get("state")) for service_id, row in rows_by_id.items()}
    effective_states = dict(local_states)

    for _ in range(max(1, len(rows_by_id) + 1)):
        changed = False
        next_states = dict(effective_states)
        for service_id, local_state in local_states.items():
            target_states = [
                _dependency_target_state(
                    relation.target,
                    effective_states=effective_states,
                    rows_by_id=rows_by_id,
                )
                for relation in required.get(service_id, [])
            ]
            resolved = _effective_state(local_state, _dependency_state(target_states))
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
        target_effective_states = [effective_states.get(relation.target, "unknown") for relation in relations]
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
        row.update(
            {
                "state": effective_state,
                "local_state": local_state,
                "dependency_state": dependency_state,
                "effective_state": effective_state,
                "required_dependencies": [relation.target for relation in relations],
                "blocked_by": [relation.target for relation, state in zip(relations, target_states, strict=True) if state == "fail"],
                "degraded_by": [relation.target for relation, state in zip(relations, target_states, strict=True) if state == "warn"],
                "unconfirmed_dependencies": [relation.target for relation, state in zip(relations, target_states, strict=True) if state == "unknown"],
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
            },
        )
        result.append(row)
    return result
