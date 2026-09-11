"""Static contract tests for the additive service operator diagnostics UI."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "nabla" / "api" / "assets"


def test_operator_diagnostics_is_installed_without_new_backend_probe_contract() -> None:
    health = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")

    assert 'installServiceOperatorDiagnostics' in health
    assert 'fetchHealthBoard()' in source
    assert 'fetchTopology()' in source
    assert 'health-board-refreshed' in source
    assert '/api/' not in source


def test_truenas_runtime_badges_restore_app_and_container_states() -> None:
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")

    assert 'active_workloads' in source
    assert 'container_details' in source
    assert 'data-runtime-badge' not in source  # dataset API keeps markup implementation-neutral.
    assert 'dataset.runtimeBadge' in source
    assert 'App ${String(runtimeState).toUpperCase()}' in source
    assert '🐳 ${name} ${String(state).toUpperCase()}' in source
    assert 'starting' in source
    assert 'restarting' in source
    assert 'crashed' in source


def test_downstream_hover_links_to_service_anchors() -> None:
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")
    css = (ASSETS / "api-service-operator-diagnostics.css").read_text(encoding="utf-8")

    assert 'health-downstream-badge' in source
    assert 'Downstream impact' in source
    assert 'link.href = `#${anchors.get(id) || `service-${id}`}`' in source
    assert 'service-hover-popover' in source
    assert ':hover > .service-hover-popover' in css
    assert ':focus-within > .service-hover-popover' in css


def test_service_drawer_adds_dependencies_runtime_and_performance() -> None:
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")

    assert 'TrueNAS / Docker runtime' in source
    assert 'Dependencies & downstream' in source
    assert 'Depends on' in source
    assert 'Direct downstream' in source
    assert 'Transitive downstream' in source
    assert 'Service performance' in source
    assert 'Probe latency' in source
    assert 'Evidence age' in source
    assert 'Probe interval' in source


def test_probe_strip_adds_external_boolean_and_prometheus_without_legacy_duplication() -> None:
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")

    assert 'external=true' in source
    assert 'external=false' in source
    assert '"Prometheus"' in source
    assert '/\\/metrics(?:$|[?#])/i' in source
    assert 'cleanDuplicatedExposureNote' in source
    assert '^Cloudflare expected$' in source
    assert '^Service token Access ' in source


def test_question_mark_help_explains_independent_evidence_layers() -> None:
    source = (ASSETS / "api-service-operator-diagnostics.js").read_text(encoding="utf-8")

    assert 'badge.textContent = "?"' in source
    assert 'How to read this service' in source
    assert 'Runtime, reachability, dependencies and edge security are independent evidence layers.' in source
