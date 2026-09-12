"""Static contracts for topology operator controls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_topology_page_exposes_shape_legend_and_operator_controls() -> None:
    page = (ROOT / "nabla" / "api" / "topology_ui.py").read_text(encoding="utf-8")

    for marker in (
        'id="topology-group-by"',
        'id="topology-hide-docker"',
        'id="topology-node-sizing"',
        'id="topology-edge-sizing"',
        "standard node",
        "security control",
        "operator group",
        "CPU + RAM telemetry",
        "Observed bandwidth",
    ):
        assert marker in page
    assert "/api/assets/api-topology-capture.js" in page
    assert "/api/assets/api-topology-operator.js" in page


def test_topology_operator_hides_docker_and_groups_by_lifecycle_without_guessing_networks() -> None:
    javascript = (ASSETS / "api-topology-operator.js").read_text(encoding="utf-8")

    assert 'graph.getElementById("docker")' in javascript
    assert 'edge.data("relationType") === "hostedBy"' in javascript
    assert 'mode === "lifecycle"' in javascript
    assert 'mode === "docker-network"' in javascript
    assert "waiting for canonical network-membership metadata" in javascript
    assert "no network is guessed from names" in javascript


def test_topology_operator_scales_nodes_from_cpu_ram_and_refuses_unattributed_edges() -> None:
    javascript = (ASSETS / "api-topology-operator.js").read_text(encoding="utf-8")

    assert "resource.cpu_cores" in javascript
    assert "resource.memory_bytes" in javascript
    assert "Math.sqrt(pressure)" in javascript
    assert "telemetry?.edge_bandwidth" in javascript
    assert "Per-edge bandwidth attribution is unavailable" in javascript
    assert 'fetchJson("/api/topology-telemetry")' in javascript


def test_topology_telemetry_route_is_registered() -> None:
    routes = (ROOT / "nabla" / "routes.py").read_text(encoding="utf-8")

    assert 'app.get("/api/topology-telemetry"' in routes
    assert "await fetch_topology_telemetry()" in routes
