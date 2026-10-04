"""Tests for dependency-aware homelab health propagation."""

from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_health_evidence import (
    _append_runtime_topology_component_evidence,
    _reconcile_shared_component_evidence,
)
from nabla.api.homelab_runtime import runtime_snapshot_from_health_api
from nabla.api.homelab_topology import HomelabTopology


def _row(service_id: str, state: str, **extra: object) -> dict[str, object]:
    return {
        "id": service_id,
        "name": service_id,
        "url": f"https://{service_id}.albandrieu.com/",
        "reachable": state == "ok",
        "http_status": 200 if state == "ok" else 0,
        "state": state,
        **extra,
    }


def _relation(
    source: str,
    target: str,
    *,
    relation_type: str = "dependsOn",
    strength: str = "required",
) -> dict[str, object]:
    return {
        "source": source,
        "target": target,
        "type": relation_type,
        "strength": strength,
        "description": f"{source} uses {target}",
        "evidence": [f"tests:{source}->{target}"],
    }


def _topology(*relations: dict[str, object]) -> HomelabTopology:
    ids = {str(value) for relation in relations for value in (relation["source"], relation["target"])}
    return HomelabTopology.model_validate(
        {
            "nodes": [
                {
                    "id": service_id,
                    "name": service_id.replace("-", " ").title(),
                    "kind": "service",
                    "category": "test",
                }
                for service_id in sorted(ids)
            ],
            "relations": list(relations),
        },
    )


def test_confirmed_failed_dependencies_degrade_running_service() -> None:
    topology = _topology(
        _relation("n8n", "postgresql"),
        _relation("litellm", "ollama", relation_type="consumesApi"),
    )
    rows = propagate_required_dependency_health(
        [
            _row("n8n", "ok"),
            _row("postgresql", "fail"),
            _row("litellm", "ok"),
            _row("ollama", "fail"),
        ],
        topology,
    )
    by_id = {str(row["id"]): row for row in rows}

    assert by_id["n8n"]["effective_state"] == "warn"
    assert by_id["n8n"]["blocked_by"] == ["postgresql"]
    assert by_id["litellm"]["effective_state"] == "warn"
    assert by_id["litellm"]["blocked_by"] == ["ollama"]


def test_unknown_dependency_does_not_override_fresh_http_success() -> None:
    rows = propagate_required_dependency_health(
        [_row("n8n", "ok")],
        _topology(_relation("n8n", "postgresql")),
    )
    n8n = rows[0]

    assert n8n["local_state"] == "ok"
    assert n8n["dependency_state"] == "unknown"
    assert n8n["effective_state"] == "ok"
    assert n8n["blocked_by"] == []
    assert n8n["degraded_by"] == []
    assert n8n["unconfirmed_dependencies"] == ["postgresql"]


def test_stale_dependency_is_unconfirmed_not_blocking() -> None:
    rows = propagate_required_dependency_health(
        [
            _row("service", "ok"),
            _row(
                "database",
                "fail",
                observed_at="2000-01-01T00:00:00Z",
                observation_age_seconds=120,
                observation_stale=True,
            ),
        ],
        _topology(_relation("service", "database")),
    )
    service = rows[0]
    evidence = service["dependency_evidence"][0]

    assert service["effective_state"] == "ok"
    assert service["blocked_by"] == []
    assert service["unconfirmed_dependencies"] == ["database"]
    assert evidence["target_state"] == "unknown"
    assert evidence["target_effective_state"] == "fail"
    assert evidence["target_observation_stale"] is True


def test_warn_dependency_degrades_but_does_not_claim_blocked() -> None:
    rows = propagate_required_dependency_health(
        [_row("consumer", "ok"), _row("proxy", "warn")],
        _topology(_relation("consumer", "proxy", relation_type="routesTo")),
    )
    consumer = rows[0]

    assert consumer["effective_state"] == "warn"
    assert consumer["blocked_by"] == []
    assert consumer["degraded_by"] == ["proxy"]
    assert consumer["unconfirmed_dependencies"] == []


def test_optional_and_structural_relations_do_not_change_health() -> None:
    topology = _topology(
        _relation("openwebui", "searxng", strength="optional"),
        _relation("openwebui", "docker", relation_type="hostedBy"),
    )
    rows = propagate_required_dependency_health(
        [_row("openwebui", "ok"), _row("searxng", "fail"), _row("docker", "fail")],
        topology,
    )
    openwebui = rows[0]

    assert openwebui["state"] == "ok"
    assert openwebui["required_dependencies"] == []


def test_confirmed_degradation_propagates_across_dependency_chain() -> None:
    topology = _topology(
        _relation("openwebui", "litellm", relation_type="consumesApi"),
        _relation("litellm", "ollama", relation_type="consumesApi"),
    )
    rows = propagate_required_dependency_health(
        [_row("openwebui", "ok"), _row("litellm", "ok"), _row("ollama", "fail")],
        topology,
    )
    by_id = {str(row["id"]): row for row in rows}

    assert by_id["litellm"]["effective_state"] == "warn"
    assert by_id["litellm"]["blocked_by"] == ["ollama"]
    assert by_id["openwebui"]["effective_state"] == "warn"
    assert by_id["openwebui"]["degraded_by"] == ["litellm"]


def test_required_cycles_are_surfaced_without_recursive_walks() -> None:
    topology = _topology(
        _relation("service-a", "service-b"),
        _relation("service-b", "service-c"),
        _relation("service-c", "service-a"),
    )
    rows = propagate_required_dependency_health(
        [_row("service-a", "ok"), _row("service-b", "ok"), _row("service-c", "ok")],
        topology,
    )

    for row in rows:
        assert row["dependency_cycle"] == ["service-a", "service-b", "service-c"]
        assert row["effective_state"] == "ok"


def test_local_failure_remains_failure_when_dependency_is_healthy() -> None:
    rows = propagate_required_dependency_health(
        [_row("service", "fail"), _row("database", "ok")],
        _topology(_relation("service", "database")),
    )
    assert rows[0]["effective_state"] == "fail"
    assert rows[0]["dependency_state"] == "ok"


def test_runtime_topology_projection_resolves_redis_and_kafka() -> None:
    topology = HomelabTopology.model_validate(
        {
            "nodes": [
                {
                    "id": "sentry",
                    "name": "Sentry",
                    "kind": "service",
                    "category": "observability",
                },
                {
                    "id": "redis",
                    "name": "Redis",
                    "kind": "cache",
                    "category": "data",
                    "runtime": {
                        "provider": "truenas-app",
                        "containerService": "redis",
                    },
                },
                {
                    "id": "kafka",
                    "name": "Apache Kafka",
                    "kind": "message-broker",
                    "category": "data",
                    "runtime": {
                        "provider": "truenas-app",
                        "containerService": "kafka",
                    },
                },
            ],
            "relations": [
                _relation("sentry", "redis"),
                _relation("sentry", "kafka"),
            ],
        },
    )
    runtime = runtime_snapshot_from_health_api(
        {
            "reachable": True,
            "last_success_at": "2026-10-04T10:22:49Z",
            "apps": [
                {
                    "id": "redis",
                    "name": "redis",
                    "state": "RUNNING",
                    "active_workloads": {
                        "container_details": [
                            {"service_name": "redis", "state": "running"},
                        ],
                    },
                },
                {
                    "id": "kafka",
                    "name": "kafka",
                    "state": "RUNNING",
                    "active_workloads": {
                        "container_details": [
                            {"service_name": "kafka", "state": "running"},
                        ],
                    },
                },
            ],
        },
    )
    assert runtime is not None

    rows = _append_runtime_topology_component_evidence(
        [_row("sentry", "fail", runtime_state="CRASHED")],
        topology=topology,
        runtime=runtime,
    )
    reconciled = propagate_required_dependency_health(rows, topology)
    by_id = {str(row["id"]): row for row in reconciled}

    assert by_id["redis"]["state"] == "ok"
    assert by_id["redis"]["topology_runtime_projection"] is True
    assert by_id["kafka"]["state"] == "ok"
    assert by_id["sentry"]["dependency_state"] == "ok"
    assert by_id["sentry"]["unconfirmed_dependencies"] == []
    assert by_id["sentry"]["effective_state"] == "fail"


def test_postgres_sql_success_prevents_false_sentry_dependency_block() -> None:
    topology = _topology(_relation("sentry", "postgresql"))
    rows = _reconcile_shared_component_evidence(
        [
            _row("sentry", "fail", runtime_state="CRASHED"),
            _row("postgresql", "fail", runtime_state="RUNNING"),
        ],
        {"postgres": {"reachable": True}},
    )

    reconciled = propagate_required_dependency_health(rows, topology)
    by_id = {str(row["id"]): row for row in reconciled}

    assert by_id["postgresql"]["state"] == "ok"
    assert by_id["postgresql"]["component_probe_kind"] == "sql_query"
    assert by_id["sentry"]["dependency_state"] == "ok"
    assert by_id["sentry"]["blocked_by"] == []
    assert by_id["sentry"]["effective_state"] == "fail"
