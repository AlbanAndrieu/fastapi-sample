"""Contracts for the standalone Cytoscape homelab topology screen."""

from pathlib import Path

from nabla.api.topology_ui import render_topology_page

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_topology_page_is_separate_from_health_dashboard() -> None:
    page = render_topology_page(title_suffix="test", app_version="1.2.3")

    assert "Homelab topology" in page
    assert 'href="/api"' in page
    assert 'href="/api/homelab-topology"' in page
    assert "/api/assets/api-topology.css?v=1.2.3" in page
    assert "/api/assets/api-topology.js?v=1.2.3" in page
    assert 'id="health-board"' not in page


def test_topology_page_pins_cytoscape_with_subresource_integrity() -> None:
    page = render_topology_page(title_suffix="test", app_version="1.2.3")

    assert "/cytoscape/3.33.1/cytoscape.min.js" in page
    assert 'integrity="sha512-' in page
    assert 'crossorigin="anonymous"' in page
    assert 'referrerpolicy="no-referrer"' in page
    assert "latest" not in page


def test_topology_client_reuses_declared_contract_and_classification() -> None:
    script = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'from "./api-service-classification.js"' in script
    assert 'from "./api-topology-data.js"' in script
    assert "analyzeTopology(topology)" in script
    assert "transitiveDependents" in script
    assert "directDependencies" in script
    assert "window.cytoscape" in script
    assert 'strength = "optional"' in script
    assert 'name: "cose"' in script


def test_shared_topology_loader_keeps_existing_fallback_contract() -> None:
    script = (ASSETS / "api-topology-data.js").read_text(encoding="utf-8")

    assert 'fetchJson("/api/homelab-topology")' in script
    assert 'fetchJson("/api/homelab/declared-services")' in script
    assert 'source: "declared-services-fallback"' in script
    assert 'source: "classification-unavailable"' in script
    assert 'cache: "no-store"' in script


def test_topology_route_is_registered_without_changing_api_page() -> None:
    routes = (ROOT / "nabla" / "routes.py").read_text(encoding="utf-8")
    api_page = (ROOT / "nabla" / "api" / "ui.py").read_text(encoding="utf-8")

    assert 'app.get("/api/topology"' in routes
    assert "_register_topology_dashboard(app)" in routes
    assert "render_topology_page(" in routes
    assert 'href="/api/topology">Topology</a>' in api_page
    assert "cytoscape" not in api_page.lower()
