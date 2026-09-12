"""Static contracts for stable health-board evidence and diagnostics."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_consistency_precedes_probe_grid_and_final_layer() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-health-ui-consistency-followup.js"' in entrypoint
    assert 'from "./api-health-ui-probe-grid.js"' in entrypoint
    assert entrypoint.index("installHealthUiConsistencyFollowup();") < entrypoint.index(
        "installHealthUiProbeGrid();",
    )
    assert entrypoint.index("installHealthUiProbeGrid();") < entrypoint.index(
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


def test_probe_grid_has_fixed_order_and_neutral_startup_slots() -> None:
    source = (ASSETS / "api-health-ui-probe-grid.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    expected = [
        '["dns", "🧭", "DNS"]',
        '["http", "🌐", "HTTP"]',
        '["tls", "🔒", "TLS"]',
        '["cloudflare", "☁️", "Tunnel"]',
        '["access", "🛡️", "Access"]',
        '["service-token", "🔑", "Token"]',
        '["api", "⚙️", "API"]',
        '["policy", "🛡️", "Policy"]',
        '["tcp", "🔌", "TCP"]',
        '["websocket", "↔", "WebSocket"]',
        '["metrics", "📈", "Prometheus"]',
    ]
    positions = [source.index(item) for item in expected]
    assert positions == sorted(positions)
    assert "probeTone(source)" in source
    assert 'return "neutral"' in source
    assert "grid-template-columns: repeat(11" in stylesheet
    assert "service-probe-table-cell--neutral" in stylesheet


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
    assert "removeDuplicateProviderItems" in source
    assert "removeCloudflareSummaryDuplicates" in source
    assert 'providerItem(section, "Access applications")' in source
    assert 'providerItem(section, "Reusable policies")' in source
    assert 'providerItem(section, "Service Tokens")' in source
    assert "application\\(s\\) visible" in source
    assert "policy object\\(s\\) visible" in source
    assert "service token\\(s\\) visible" in source
    assert 'appError || "inventory confirmed"' in source
    assert "policyError || PROJECT_ACCESS_POLICY" in source
    assert "`${PROJECT_SERVICE_AUTH} · ${tokenPresence}`" in source


def test_filter_and_drawer_reserve_fixed_visual_space() -> None:
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )
    final_stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    assert ".service-detail-evidence" in stylesheet
    assert "left: 0" in stylesheet
    assert "width: 470px" in stylesheet or "width: 470px" in (
        ASSETS / "api-health-ui-responsive-followup.js"
    ).read_text(encoding="utf-8")
    assert ".service-probe-table" in final_stylesheet
    assert "min-width: 52rem" in final_stylesheet
    assert "grid-template-columns: repeat(2" in final_stylesheet
