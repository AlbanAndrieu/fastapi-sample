"""Tests for dependency-aware homelab health propagation."""

from nabla.api.homelab_dependency_health import propagate_required_dependency_health
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
