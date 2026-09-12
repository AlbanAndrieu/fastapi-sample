"""Static contracts for the health-board operator follow-up."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_operator_followup_is_installed_after_other_health_ui_layers() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-health-ui-operator-followup.js"' in entrypoint
    assert entrypoint.index("installHealthUiOperatorFollowup();") > entrypoint.index(
        "installHealthUiProbeExplanations();",
    )


def test_truenas_core_drilldown_is_pinned_outside_service_filter_results() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'getElementById("truenas-platform")' in source
    assert "panel.hidden = false" in source
    assert 'panel.dataset.filterPinned = "true"' in source
    assert 'document.addEventListener("service-filter-changed", schedule)' in source


def test_pfsense_posture_renders_latest_and_keeps_bounded_history() -> None:
    source = (ASSETS / "api-pfsense-security-posture.js").read_text(
        encoding="utf-8",
    )

    assert "HISTORY_LIMIT = 50" in source
    assert "container.replaceChildren()" in source
    assert "pfsense-security-posture-history" in source
    assert "postureHistory.splice(HISTORY_LIMIT)" in source


def test_flow_links_public_dns_cloudflare_and_truenas_api_diagnostics() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'document.createTextNode("Public DNS · ")' in source
    assert "CLOUDFLARE_ICON" in source
    assert '"cloudflare"' in source
    assert 'label.includes("truenas api")' in source
    assert "openTrueNasDiagnostics" in source


def test_legacy_sickz_label_uses_authoritative_catalog_description() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'fetch("/api/homelab-services"' in source
    assert "service?.description" in source
    assert 'includes("Legacy inverse-reachability target")' in source
    assert "tags.textContent = description" in source


def test_cloudflare_inventory_failure_is_not_rendered_as_zero_inventory() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'family.success === false || family.state === "error"' in source
    assert "inventory unavailable" in source
    assert "Access Apps and Policies Read" in source
    assert "Access Service Tokens Read" in source


def test_local_runtime_notices_and_pfsense_evidence_are_reconciled() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert "HOMELAB_INTERNAL_PROBES_ENABLED=false" in source
    assert "RUNTIME_DIAGNOSTICS_ENABLED=false" in source
    assert 'fetch("/v1/runtime/metadata"' in source
    assert 'runtime_mode !== "local"' in source
    assert "pfSense REST/API reachability is independently confirmed" in source
    assert 'led.className = "health-led health-led--blue"' in source


def test_probe_evidence_and_plane_links_are_deduplicated() -> None:
    source = (ASSETS / "api-health-ui-operator-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'querySelectorAll("[data-probe-kind]")' in source
    assert "badges.reverse()" in source
    assert 'querySelectorAll(":scope > .health-row-telemetry")' in source
    assert ".service-probe-plane-label--public" in source
    assert ".service-probe-plane-label--lan" in source
    assert "strong.replaceChildren(link)" in source


def test_responsive_css_stabilizes_metrics_and_widens_desktop_filter() -> None:
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )

    assert "font-variant-numeric: tabular-nums" in stylesheet
    assert ".service-detail-metric strong" in stylesheet
    assert "min-height: 1.2rem" in stylesheet
    assert ".service-provider-item > div > span" in stylesheet
    assert "width: 420px" in stylesheet
    assert "margin-left: 450px" in stylesheet
    assert ".service-probe-legend" in stylesheet
    assert "flex-wrap: wrap" in stylesheet
