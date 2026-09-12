"""Contracts for the page-wide sticky service-health filter shell."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_entrypoint_installs_one_global_filter_shell() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")

    assert 'from "./api-global-service-filter.js"' in entrypoint
    assert entrypoint.count("installGlobalServiceFilter();") == 1
    assert 'document.querySelector(".service-filter")' in shell
    assert 'board.insertAdjacentElement("beforebegin", host);' in shell
    assert 'host.classList.add("service-filter--global")' in shell
    assert "Service health and filters" in shell
    assert "Global view" in shell
    assert "Cards are the canonical operational view" in shell


def test_global_filter_mirrors_site_health_summary_without_second_engine() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    engine = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")
    diagnostics = (ASSETS / "api-service-diagnostics.js").read_text(encoding="utf-8")

    for status in ("Operational", "At risk", "Degraded", "Down", "Unknown"):
        assert status in shell
    assert 'select.dispatchEvent(new Event("change", { bubbles: true }));' in shell
    assert "service-status-filter" in shell
    assert "function refreshServiceFilter()" not in shell
    assert "export function refreshServiceFilter()" in engine
    assert "refreshServiceFilter();" in diagnostics


def test_global_filter_stays_visible_and_compacts_secondary_help() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(encoding="utf-8")

    assert "position: sticky" in stylesheet
    assert "service-filter-health-summary" in stylesheet
    assert "service-filter-legend-details" in stylesheet
    assert "Legend / how to read" in shell
    assert '.service-filter--global[data-stuck="true"][data-expanded="true"]' in stylesheet
    assert "max-height: calc(100dvh" in stylesheet
    assert "focus-visible" in stylesheet
    assert 'window.addEventListener("scroll", refreshSticky' in shell
    assert "STICKY_HYSTERESIS_PX" in shell
    assert "new IntersectionObserver(" not in shell
    assert 'host.classList.toggle("service-filter--compact", compact);' in shell
    assert 'id="service-filter-density-toggle"' in shell
    assert "Collapse" in shell
    assert ".service-filter--compact .service-filter-facets" in stylesheet
    assert ".service-filter--compact .service-filter-health-summary" in stylesheet


def test_active_filter_chips_remove_individual_filters() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(encoding="utf-8")

    assert "service-filter-active" in shell
    assert "service-filter-active-chip" in shell
    assert 'document.addEventListener("service-filter-changed"' in shell
    assert "control.dispatchEvent(" in shell
    assert 'key === "query" ? "input" : "change"' in shell
    remove_symbol = chr(0x00D7)
    assert f'remove.textContent = "{remove_symbol}";' in shell
    assert ".service-filter-active-chip" in stylesheet
    assert ".service-filter-active[hidden]" in stylesheet


def test_global_filter_supports_keyboard_and_truenas_status_sync() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")

    assert 'event.key === "/"' in shell
    assert 'event.key === "Escape"' in shell
    assert 'document.getElementById("truenas-platform")' in shell
    assert 'panel.dataset.presentationGroup = "core-critical";' in shell
    assert 'panel.dataset.environments = "production";' in shell
    assert 'panel.dataset.environmentSource = "runtime";' in shell
    assert 'panel.dataset.semanticStatus = "operational";' in shell
    assert 'panel.dataset.semanticStatus = "degraded";' in shell
    assert 'panel.dataset.semanticStatus = "down";' in shell


def test_health_legend_explains_card_flow_and_security_icons() -> None:
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    legend = (ASSETS / "api-platform-legend.js").read_text(encoding="utf-8")

    assert 'from "./api-platform-legend.js"' in bootstrap
    assert "installPlatformLegend();" in bootstrap
    assert "Cards = canonical operational state" in legend
    assert "Flow = path/dependency context" in legend
    assert '"🧱", "pfSense / PF path"' in legend
    assert '"🛡️", "Snort"' in legend
    assert '"🚫", "pfBlockerNG"' in legend
    assert '"👥", "CrowdSec"' in legend
    assert "gray = unavailable/unconfirmed" in legend
