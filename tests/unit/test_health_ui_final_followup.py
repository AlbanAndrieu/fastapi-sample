"""Static contracts for the final health-board UI follow-up."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_final_followup_is_loaded_last() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'from "./api-health-ui-final-followup.js"' in entrypoint
    assert entrypoint.rstrip().endswith("installHealthUiFinalFollowup();")
    assert stylesheet.rstrip().endswith(
        '@import url("./api-health-ui-final-followup.css");',
    )


def test_main_api_surface_uses_topology_scale_width() -> None:
    stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    assert "width: min(1600px, 100%)" in stylesheet
    assert ".cards" in stylesheet
    assert ".hero-code" in stylesheet
    assert "max-width: none" in stylesheet


def test_drawer_avoids_noop_rerenders_and_preserves_probe_links() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(
        encoding="utf-8",
    )

    assert "function drawerSignature" in source
    assert "drawer.dataset.renderSignature === signature" in source
    assert "probe instanceof HTMLAnchorElement" in source
    assert 'icon.className = "service-detail-probe-icon"' in source
    assert 'label.className = "service-detail-probe-label"' in source


def test_telemetry_moves_legacy_latency_and_shows_cloudflare_unknown() -> None:
    source = (ASSETS / "api-health-ui-final-followup.js").read_text(
        encoding="utf-8",
    )

    assert 'querySelectorAll(".health-meta-badge--metric")' in source
    assert "Latest probe latency" in source
    assert 'unavailable.textContent = "-"' in source
    assert "health-meta-badge--probe-latency-unavailable" in source


def test_transitive_downstream_matches_direct_list_typography() -> None:
    stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    assert ".service-detail-relations .service-hover-list a" in stylesheet
    assert "display: list-item" in stylesheet
    assert "list-style-type: disc" in stylesheet
    assert "font-size: 0.61rem" in stylesheet


def test_sickz_card_keeps_verbose_help_in_drawer() -> None:
    source = (ASSETS / "api-health-ui-final-followup.js").read_text(
        encoding="utf-8",
    )
    stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    assert "cleanExposureCardInlineDetails" in source
    assert "legacy inverse-reachability target" in source
    assert "#sickz-checks .health-row-tags .service-hover-popover" in stylesheet


def test_cloudflare_tunnel_capability_is_retained_when_inventory_flaps() -> None:
    source = (ASSETS / "api-health-ui-final-followup.js").read_text(
        encoding="utf-8",
    )

    assert "ensureStableCloudflareTunnel" in source
    assert 'badge.dataset.probeKind = "cloudflare"' in source
    assert 'badge.className = "service-probe service-probe--neutral"' in source
    assert "Cloudflare Tunnel evidence is currently unavailable" in source


def test_topology_warns_when_dev_tunnel_carries_production_service() -> None:
    source = (ASSETS / "api-topology-health.js").read_text(encoding="utf-8")

    assert '["nabla-albandrieu", "development"]' in source
    assert '["nabla-truescale", "production"]' in source
    assert "Cloudflare environment mismatch" in source
    assert 'environmentWarning && effective === "ok" ? "warn"' in source
