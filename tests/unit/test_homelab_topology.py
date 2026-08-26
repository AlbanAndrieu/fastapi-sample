"""Contract tests for the declared homelab service topology."""

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.testclient import TestClient

from nabla.api import homelab_topology
from nabla.api.health_routes import register_health_routes
from nabla.api.homelab_topology import HomelabTopology


def _topology_payload() -> dict:
    return {
        "version": 1,
        "name": "test topology",
        "nodes": [
            {
                "id": "openwebui",
                "name": "Open WebUI",
                "kind": "application",
                "category": "ai",
                "sourcePath": "apps/openwebui/compose.yml",
                "icon": "💬",
            },
            {
                "id": "litellm",
                "name": "LiteLLM",
                "kind": "gateway",
                "category": "ai",
            },
        ],
        "relations": [
            {
                "source": "openwebui",
                "target": "litellm",
                "type": "consumesApi",
                "strength": "required",
                "evidence": ["apps/openwebui/compose.yml:OPENAI_API_BASE_URL"],
            }
        ],
    }


def test_topology_accepts_declared_relation_and_preserves_wire_aliases() -> None:
    topology = HomelabTopology.model_validate(_topology_payload())

    payload = topology.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert topology.nodes[0].source_path == "apps/openwebui/compose.yml"
    assert topology.nodes[0].icon == "💬"
    assert payload["nodes"][0]["sourcePath"] == "apps/openwebui/compose.yml"
    assert payload["nodes"][0]["icon"] == "💬"
    assert payload["relations"][0]["type"] == "consumesApi"


def test_topology_endpoint_returns_validated_service_graph(monkeypatch) -> None:
    topology = HomelabTopology.model_validate(_topology_payload())

    async def fetch_topology() -> HomelabTopology:
        return topology

    monkeypatch.setattr(homelab_topology, "fetch_homelab_topology", fetch_topology)
    app = FastAPI()
    register_health_routes(app)

    response = TestClient(app).get("/api/homelab-topology")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"][0]["sourcePath"] == "apps/openwebui/compose.yml"
    assert payload["nodes"][0]["icon"] == "💬"
    assert payload["relations"][0]["type"] == "consumesApi"


def test_topology_rejects_unknown_relation_target() -> None:
    payload = _topology_payload()
    payload["relations"][0]["target"] = "missing-service"

    with pytest.raises(ValidationError, match="unknown node"):
        HomelabTopology.model_validate(payload)


def test_topology_rejects_duplicate_node_id() -> None:
    payload = _topology_payload()
    payload["nodes"].append(dict(payload["nodes"][0]))

    with pytest.raises(ValidationError, match="duplicate homelab topology node id"):
        HomelabTopology.model_validate(payload)


def test_topology_rejects_self_relation() -> None:
    payload = _topology_payload()
    payload["relations"][0]["target"] = "openwebui"

    with pytest.raises(ValidationError, match="source and target must differ"):
        HomelabTopology.model_validate(payload)
