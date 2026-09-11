"""Contracts for topology view presets and shareable browser state."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_topology_presets_use_declared_relation_types_only() -> None:
    source = (ASSETS / "api-topology-filter-state.js").read_text(encoding="utf-8")

    for relation_type in (
        "dependsOn",
        "consumesApi",
        "providesApi",
        "storesIn",
        "authenticatesVia",
    ):
        assert f'"{relation_type}"' in source
    assert 'new Set(["routesTo", "exposedBy"])' in source
    assert 'return "architecture";' in source
    assert "url.includes(" not in source
    assert "hostname" not in source.lower()


def test_topology_default_view_is_dependencies_and_exact_relation_overrides_it() -> None:
    state_source = (ASSETS / "api-topology-filter-state.js").read_text(
        encoding="utf-8",
    )
    topology_source = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'DEFAULT_TOPOLOGY_PRESET = "dependencies"' in state_source
    assert 'relation !== DEFAULTS.relation && preset !== "all"' in state_source
    assert 'presetSelect.value = "all";' in state_source
    assert 'relation.value !== "all" && preset' in topology_source
    assert 'preset.value = "all";' in topology_source


def test_topology_filter_state_is_shareable_without_server_side_session() -> None:
    source = (ASSETS / "api-topology-filter-state.js").read_text(encoding="utf-8")

    assert "new URLSearchParams(window.location.search)" in source
    assert "new URL(window.location.href)" in source
    for param in (
        "q",
        "view",
        "relation",
        "strength",
        "phase",
        "health",
        "layout",
    ):
        assert f'"{param}"' in source
    assert '"topology-lifecycle-filter"' in source
    assert '"topology-health-overlay"' in source
    assert "window.history.replaceState(" in source
    assert "${url.pathname}${url.search}${url.hash}" in source
    assert "sessionStorage" not in source
    assert "localStorage" not in source


def test_topology_history_navigation_rehydrates_the_same_controls() -> None:
    source = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'window.addEventListener("popstate"' in source
    assert "hydrateTopologyControlsFromUrl();" in source
    assert "syncHealthOverlay();" in source
    assert "applyFilters();" in source
    assert "runLayout();" in source


def test_focused_topology_views_remove_unrelated_orphan_nodes() -> None:
    source = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'preset !== "all" || relation !== "all" || strength !== "all"' in source
    assert 'node.connectedEdges().not(".is-filtered")' in source
    assert "visibleEdges.length === 0" in source
    assert 'if (!query && lifecycle === "all" && focusedRelations)' in source


def test_lifecycle_filter_uses_declared_node_metadata_only() -> None:
    source = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert 'node.data("lifecyclePhase") !== lifecycle' in source
    assert 'document.getElementById("topology-lifecycle-filter")' in source
    assert "lifecycle.phase" in source
    assert "lifecyclePriority" in source
    assert "runtimeAppId" in source
    assert "startOrder" not in source
    assert "startupOrder" not in source


def test_reset_returns_to_canonical_default_and_cleans_url_state() -> None:
    state_source = (ASSETS / "api-topology-filter-state.js").read_text(
        encoding="utf-8",
    )
    topology_source = (ASSETS / "api-topology.js").read_text(encoding="utf-8")

    assert "resetTopologyControls" in topology_source
    assert "syncTopologyControlsToUrl();" in topology_source
    assert "preset.value = DEFAULT_TOPOLOGY_PRESET;" in state_source
    assert "phase.value = DEFAULTS.phase;" in state_source
    assert "health.value = DEFAULTS.health;" in state_source
    assert "params.delete(key);" in state_source
