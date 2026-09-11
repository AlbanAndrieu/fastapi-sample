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


def test_topology_page_separates_dependency_and_network_path_views() -> None:
    page = render_topology_page(title_suffix="test", app_version="1.2.3")

    assert 'id="topology-view-preset"' in page
    assert '<option value="dependencies" selected>Dependencies</option>' in page
    assert '<option value="network-paths">Network paths</option>' in page
    assert '<option value="all">All relations</option>' in page
    assert "network/service relations" in page
    assert "network path" in page


def test_topology_page_exposes_canonical_lifecycle_without_deriving_start_order() -> None:
    page = render_topology_page(title_suffix="test", app_version="1.2.3")
    script = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'id="topology-lifecycle-filter"' in page
    for phase in (
        "bootstrap-runtime",
        "foundation",
        "network-edge",
        "primary-data",
        "secondary-data",
        "platform-services",
        "applications",
    ):
        assert f'value="{phase}"' in page
    assert "do not reproduce the operational start planner" in page
    assert 'addDetail(list, "Runtime provider"' in script
    assert 'addDetail(list, "TrueNAS App"' in script
    assert '"Lifecycle phase"' in script
    assert '"Lifecycle priority"' in script
    assert "startOrder" not in script
    assert "startupOrder" not in script


def test_topology_health_overlay_reuses_server_authoritative_evidence() -> None:
    page = render_topology_page(title_suffix="test", app_version="1.2.3")
    topology = (ASSETS / "api-topology.js").read_text(encoding="utf-8")
    overlay = (ASSETS / "api-topology-health.js").read_text(encoding="utf-8")

    assert 'id="topology-health-overlay"' in page
    assert '<option value="off">Declared only</option>' in page
    assert '<option value="on">Overlay health</option>' in page
    assert "never probes services from the browser" in page
    assert 'from "./api-topology-health.js"' in topology
    assert 'from "./api-health-board.js"' in overlay
    assert 'from "./api-health-dependency.js"' in overlay
    assert "fetchHealthBoard()" in overlay
    assert "snapshot?.homelab?.services" in overlay
    assert "effective_state" in overlay
    assert "local_state" in overlay
    assert "dependency_evidence" in overlay
    assert "target_state" in overlay
    assert "fetch(" not in overlay
    assert "XMLHttpRequest" not in overlay


def test_required_edge_overlay_uses_dependency_evidence_only() -> None:
    overlay = (ASSETS / "api-topology-health.js").read_text(encoding="utf-8")

    assert 'edge.data("strength") !== "required"' in overlay
    assert 'String(entry?.target || "") === String(target)' in overlay
    assert 'String(entry?.relation_type || "") === String(relationType)' in overlay
    assert "match.target_state" in overlay
    assert "hostname" not in overlay.lower()
    assert "url.includes(" not in overlay


def test_topology_client_reuses_declared_contract_and_classification() -> None:
    script = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'from "./api-service-classification.js"' in script
    assert 'from "./api-topology-data.js"' in script
    assert 'from "./api-topology-filter-state.js"' in script
    assert "analyzeTopology(topology)" in script
    assert "transitiveDependents" in script
    assert "directDependencies" in script
    assert "relationFamily(relation.type)" in script
    assert "presetAllowsRelation(type, preset)" in script
    assert "window.cytoscape" in script
    assert 'strength = "optional"' in script
    assert 'name: "cose"' in script


def test_shared_topology_loader_keeps_existing_fallback_contract() -> None:
    script = (ASSETS / "api-topology-data.js").read_text(encoding="utf-8")

    assert 'fetchJson("/api/homelab-topology")' in script
    assert 'fetchJson("/api/homelab/declared-services")' in script
    assert 'source: "declared-services-fallback"' in script
    assert 'source: "classification-unavailable"' in script
    assert "runtime: service?.runtime || null" in script
    assert "lifecycle: service?.lifecycle || null" in script
    assert "sourcePath: service?.sourcePath || service?.source_path || null" in script
    assert 'cache: "no-store"' in script


def test_topology_route_is_registered_without_changing_api_page() -> None:
    routes = (ROOT / "nabla" / "routes.py").read_text(encoding="utf-8")
    api_page = (ROOT / "nabla" / "api" / "ui.py").read_text(encoding="utf-8")

    assert 'app.get("/api/topology"' in routes
    assert "_register_topology_dashboard(app)" in routes
    assert "render_topology_page(" in routes
    assert 'href="/api/topology">Topology</a>' in api_page
    assert "cytoscape" not in api_page.lower()
