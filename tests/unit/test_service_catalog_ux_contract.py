"""Offline contract for service diagnostics drawers and Gatus fleet coverage."""

import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "nabla/api/assets"


def read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_drawer_links_only_observed_canonical_catalogue_rows() -> None:
    drawer = read("api-service-detail-drawer.js")
    links = read("api-service-relations.js")
    groups = read("api-service-groups.js")
    assert "fetchTopology()" in drawer
    assert "latestTopology = topology" in drawer
    assert "row.dataset.topologyId === id" in drawer
    assert "renderRelations(drawer, row)" in drawer
    assert "Upstream / dependencies" in drawer
    assert "Downstream / dependents" in drawer
    assert re.search(r"openDrawer\(\s*target", drawer)
    assert "row.dataset.topologyId = String(node.id)" in groups
    assert "ID_PATTERN" in links
    assert "nodes.has(edge.source)" in links
    assert "nodes.has(edge.target)" in links
    assert "No published dependencies" in drawer


def test_drawer_has_probe_summary_and_accessible_failure_details() -> None:
    drawer = read("api-service-detail-drawer.js")
    assert "renderProbeSummary(drawer, row)" in drawer
    assert "renderEvidence(drawer, row)" in drawer
    assert "Probe evidence" in drawer
    assert '"FAILED"' in drawer
    assert '"WARNING"' in drawer
    assert '"UNVERIFIED"' in drawer
    assert 'aria-live="polite"' in drawer
    assert "aria-haspopup" in drawer
    assert "aria-labelledby" in drawer
    assert "restoreFocus" in drawer


def test_gatus_probe_failure_does_not_claim_entire_fleet_is_green() -> None:
    summary = read("api-service-gatus-coverage.js")
    card = read("api-service-telemetry.js")
    drawer = read("api-service-detail-drawer.js")
    assert "generated_at" in summary
    assert "snapshot_stale_or_missing_timestamp" in summary
    assert "synthetic?.truncated !== true" in summary
    assert "value === 0 || value === 1" in summary
    assert "fleet.down > 0" in card
    assert '"partial_coverage"' in card
    assert "fleet.observedServices" in drawer
    assert "latestSnapshot?.platform_metrics" in drawer
    assert '["Failing checks", fleet.failures' in drawer
    assert "entries.slice(0, 25)" in drawer
    assert "This is not full catalogue coverage." in drawer


def test_no_per_card_gatus_or_prometheus_network_calls() -> None:
    summary = read("api-service-gatus-coverage.js")
    relations = read("api-service-relations.js")
    cards = read("api-service-telemetry.js")
    drawer = read("api-service-detail-drawer.js")
    for module in (summary, relations, cards):
        assert "fetch(" not in module
    assert "fetchHealthBoard()" in drawer
    assert "fetchTopology()" in drawer
    assert "/api/v1/targets" not in drawer
    assert "/api/v1/endpoints/statuses" not in drawer
    assert "eval(" not in drawer
    assert "innerHTML = " not in relations


def test_card_issue_summary_does_not_double_count_or_create_network_calls() -> None:
    cards = read("api-service-probe-planes.js")
    drawer = read("api-service-detail-drawer.js")
    assert "decorateIssueSummary(row, publicStrip);" in cards
    assert 'ensureProbe(strip, "issues", "⚠️", label)' in cards
    assert "failures.length" in cards
    assert "warnings.length" in cards
    assert 'probe.dataset.probeKind !== "issues"' in drawer
    assert "HTTP, DNS, TLS, Token and metrics evidence" in cards
    assert "this is not an overall service-down verdict" in cards
