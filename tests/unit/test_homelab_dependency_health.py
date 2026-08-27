"""Tests for dependency-aware homelab health propagation."""

from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_topology import HomelabTopology


def _row(service_id: str, state: str) -> dict[str, object]:
    return {
        "id": service_id,
        "name": service_id,
        "url": f"https://{service_id}.albandrieu.com/",
        "reachable": state == "ok",
        "http_status": 200 if state == "ok" else 0,
        "state": state,
    }


def _topology(*relations: dict[str, object]) -> HomelabTopology:
    ids = {
        str(value)
        for relation in relations
        for value in (relation["source"], relation["target"])
    }
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
        }
    )


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


def test_required_failed_dependencies_degrade_running_service() -> None:
    topology = _topology(
        _relation("langfuse-web", "postgresql"),
        _relation("langfuse-web", "clickhouse"),
        _relation("langfuse-web", "minio", relation_type="storesIn"),
    )
    rows = propagate_required_dependency_health(
        [
            _row("langfuse-web", "ok"),
            _row("postgresql", "fail"),
            _row("clickhouse", "fail"),
            _row("minio", "ok"),
        ],
        topology,
    )
    langfuse = next(row for row in rows if row["id"] == "langfuse-web")

    assert langfuse["local_state"] == "ok"
    assert langfuse["dependency_state"] == "fail"
    assert langfuse["effective_state"] == "warn"
    assert langfuse["state"] == "warn"
    assert langfuse["required_dependencies"] == ["postgresql", "clickhouse", "minio"]
    assert langfuse["blocked_by"] == ["postgresql", "clickhouse"]
    assert [item["target_state"] for item in langfuse["dependency_evidence"]] == [
        "fail",
        "fail",
        "ok",
    ]


def test_required_dependency_health_propagates_across_chains() -> None:
    topology = _topology(
        _relation("openwebui", "litellm", relation_type="consumesApi"),
        _relation("litellm", "postgresql"),
    )
    rows = propagate_required_dependency_health(
        [
            _row("openwebui", "ok"),
            _row("litellm", "ok"),
            _row("postgresql", "fail"),
        ],
        topology,
    )
    by_id = {str(row["id"]): row for row in rows}

    assert by_id["litellm"]["effective_state"] == "warn"
    assert by_id["litellm"]["blocked_by"] == ["postgresql"]
    assert by_id["openwebui"]["effective_state"] == "warn"
    assert by_id["openwebui"]["blocked_by"] == ["litellm"]
    assert by_id["openwebui"]["dependency_evidence"][0]["target_state"] == "warn"


def test_optional_and_structural_relations_do_not_change_health() -> None:
    topology = _topology(
        _relation("openwebui", "searxng", strength="optional"),
        _relation("langfuse-web", "langfuse", relation_type="partOf"),
    )
    rows = propagate_required_dependency_health(
        [
            _row("openwebui", "ok"),
            _row("searxng", "fail"),
            _row("langfuse-web", "ok"),
            _row("langfuse", "fail"),
        ],
        topology,
    )
    by_id = {str(row["id"]): row for row in rows}

    assert by_id["openwebui"]["state"] == "ok"
    assert by_id["openwebui"]["required_dependencies"] == []
    assert by_id["langfuse-web"]["state"] == "ok"
    assert by_id["langfuse-web"]["required_dependencies"] == []


def test_missing_required_target_is_visible_as_unknown_blocker() -> None:
    topology = _topology(_relation("service", "missing-db"))
    rows = propagate_required_dependency_health([_row("service", "ok")], topology)

    assert rows[0]["local_state"] == "ok"
    assert rows[0]["dependency_state"] == "unknown"
    assert rows[0]["effective_state"] == "warn"
    assert rows[0]["blocked_by"] == ["missing-db"]
    assert rows[0]["dependency_evidence"][0]["target_state"] == "unknown"


def test_local_failure_remains_failure_when_dependency_is_healthy() -> None:
    topology = _topology(_relation("service", "database"))
    rows = propagate_required_dependency_health(
        [_row("service", "fail"), _row("database", "ok")],
        topology,
    )

    assert rows[0]["local_state"] == "fail"
    assert rows[0]["dependency_state"] == "ok"
    assert rows[0]["effective_state"] == "fail"
    assert rows[0]["state"] == "fail"


def test_service_without_required_dependencies_preserves_local_state() -> None:
    rows = propagate_required_dependency_health([_row("service", "warn")], HomelabTopology())

    assert rows[0]["state"] == "warn"
    assert rows[0]["local_state"] == "warn"
    assert rows[0]["dependency_state"] is None
    assert rows[0]["effective_state"] == "warn"
    assert rows[0]["required_dependencies"] == []
    assert rows[0]["blocked_by"] == []
    assert rows[0]["dependency_evidence"] == []
