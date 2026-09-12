"""Static contracts for stable health-board evidence and diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_consistency_followup_is_installed_last() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-health-ui-consistency-followup.js"' in entrypoint
    assert entrypoint.index("installHealthUiConsistencyFollowup();") > entrypoint.index(
        "installHealthUiFinalFollowup();",
    )


def test_drawer_reattaches_when_selected_card_is_replaced() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")

    assert "let activeIdentity = null" in source
    assert "function replacementRow(identity)" in source
    assert "function reattachActiveRow()" in source
    assert 'activeRow.dataset.detailSelected = "true"' in source
    assert "if (!reattachActiveRow())" in source
    assert "closeDrawer({ restoreFocus: false })" not in source


def test_probe_capabilities_keep_stable_neutral_slots() -> None:
    source = (ASSETS / "api-health-ui-final-followup.js").read_text(
        encoding="utf-8",
    )
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )

    for probe in [
        '"dns"',
        '"http"',
        '"tls"',
        '"cloudflare"',
        '"access"',
        '"service-token"',
        '"tcp"',
    ]:
        assert probe in source
    assert "knownProbeSlots" in source
    assert "ensureProbePlaceholder" in source
    assert 'badge.dataset.probePlaceholder = "true"' in source
    assert "stabilizeProbeSlots(row)" in source
    assert 'data-probe-placeholder="true"' in stylesheet
    assert ".service-probe--neutral" in stylesheet


def test_probe_timing_uses_relative_age_and_visible_unavailable_latency() -> None:
    source = (ASSETS / "api-probe-live.js").read_text(encoding="utf-8")

    assert "Latest probe age:" in source
    assert "Latest probe latency unavailable" in source
    assert 'latencyBadge.textContent = "—"' in source
    assert "latencyBadge.hidden = false" in source
    assert "new Date(observedAt).toISOString()" not in source


def test_cloudflare_provider_reconciliation_is_project_scoped_and_deduplicated() -> None:
    source = (ASSETS / "api-health-ui-consistency-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'PROJECT_ACCESS_POLICY = "fastapi-sample-monitor"' in source
    assert 'PROJECT_SERVICE_AUTH = "fastapi-sample-monitor"' in source
    assert "keepLastSection" in source
    assert "removeDuplicateProviderItems" in source
    assert "removeCloudflareSummaryDuplicates" in source
    assert 'providerItem(section, "Access applications")' in source
    assert 'providerItem(section, "Reusable policies")' in source
    assert 'providerItem(section, "Service Tokens")' in source
    assert "project policy" in source
    assert "project Service Token" in source


def test_filter_and_drawer_reserve_fixed_visual_space() -> None:
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )

    assert ".service-detail-evidence" in stylesheet
    assert "min-height: 8.8rem" in stylesheet
    assert ".service-detail-probe" in stylesheet
    assert "min-height: 4rem" in stylesheet
    assert ".service-probe-strip" in stylesheet
    assert "grid-template-columns: repeat(auto-fit" in stylesheet
    assert "left: 0" in stylesheet
    assert "width: 430px" in stylesheet
