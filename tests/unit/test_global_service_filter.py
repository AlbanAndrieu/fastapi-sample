"""Contracts for the page-wide sticky service-health filter shell."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_entrypoint_installs_one_global_filter_shell() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")

    assert 'from "./api-global-service-filter.js"' in entrypoint
    # One call in the public branch; one after controls exist in the detailed branch.
    assert entrypoint.count("installGlobalServiceFilter();") == 2
    assert entrypoint.index("installServiceDiagnostics();") < entrypoint.rindex(
        "installGlobalServiceFilter();",
    )
    assert 'document.querySelector(".service-filter")' in shell
    assert 'board.insertAdjacentElement("beforebegin", host);' in shell
    assert 'host.classList.add("service-filter--global")' in shell
    assert "Service health and filters" in shell
    assert "Global view" in shell
    assert "Choose a status, then refine the services." in shell


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
    # #380: idempotent writes so the observed panel cannot self-trigger.
    assert 'setDatasetValueIfChanged(panel, "presentationGroup", "core-critical");' in shell
    assert 'setDatasetValueIfChanged(panel, "environments", "production");' in shell
    assert 'setDatasetValueIfChanged(panel, "environmentSource", "runtime");' in shell
    for status in ('"operational"', '"degraded"', '"down"', '"unknown"'):
        assert f"? {status}" in shell or f": {status}" in shell
    assert 'setDatasetValueIfChanged(panel, "semanticStatus", status);' in shell


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


def test_mobile_filter_uses_horizontal_rails_and_one_row_actions() -> None:
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(
        encoding="utf-8",
    )
    responsive = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )
    mobile = (ASSETS / "api-mobile.css").read_text(encoding="utf-8")

    assert "scroll-snap-type: x proximity;" in stylesheet
    assert "flex: 0 0 min(72vw, 11.5rem);" in stylesheet
    assert "min-width: 6.5rem;" in stylesheet
    assert "min-height: 44px;" in stylesheet
    assert "overscroll-behavior-inline: contain;" in stylesheet
    assert ".service-filter--global:not(.service-filter--compact)" in responsive
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in responsive
    assert "  .service-filter-control,\n  .runtime-topology-grid" not in mobile


def test_mobile_filter_is_compact_before_the_first_scroll() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")

    assert 'window.matchMedia("(max-width: 720px)").matches' in shell
    assert 'host.dataset.mobileExpanded = "false";' in shell
    assert 'mobile && host.dataset.mobileExpanded !== "true"' in shell
    assert "button.textContent = mobile" in shell
    assert '"Filters"' in shell
    assert '"Hide filters"' in shell
    assert "syncCompactState(host);" in shell


def test_section_navigation_stays_horizontal_on_mobile() -> None:
    operator = (ASSETS / "api-health-operator-ux.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-service-diagnostics.css").read_text(encoding="utf-8")

    assert 'nav.className = "service-section-navigation";' in operator
    assert "nav.style.gridTemplateColumns" not in operator
    assert "#service-section-navigation.service-section-navigation" in stylesheet
    assert "flex-direction: row;" in stylesheet
    assert "overflow-x: auto;" in stylesheet
    assert "scroll-snap-type: x proximity;" in stylesheet


def test_mobile_status_filters_are_compact_accessible_toggles() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    css = (ASSETS / "api-diagnostics-ux.css").read_text(encoding="utf-8")
    entry = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert '["all", "All"]' in shell
    assert "counts.all = rows.length;" in shell
    assert "STATUS_ICON_PATHS" in shell
    assert 'button.setAttribute("aria-pressed", String(enabled));' in shell
    assert "button.dataset.tooltip" in shell
    assert 'button.setAttribute("aria-label"' in shell
    assert 'select.dispatchEvent(new Event("change", { bubbles: true }));' in shell
    assert "service-filter-health-count" in css
    assert "repeat(6, minmax(44px, 1fr))" in css
    assert "service-filter-health-chip:focus-visible::after" in css
    assert "service-filter-health-chip:active::after" in css
    assert "service-filter--compact #service-protocol-shortcuts" in css
    assert "api-diagnostics-ux.css" in entry


def test_accessible_disclosure_contract() -> None:
    script = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    assert 'aria-controls="service-filter-advanced"' in script
    assert 'button.setAttribute("aria-label", label);' in script
    assert 'button.setAttribute("aria-describedby"' in script
    assert "advanced.hidden = compact;" in script


def test_mobile_disclosure_respects_touch_and_keyboard() -> None:
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    entry = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    assert 'host.dataset.mobileExpanded = "true";' in shell
    assert 'host.dataset.userCompact = "false";' in shell
    assert 'document.getElementById("service-filter")?.focus();' in shell
    assert "const compact = mobile" in shell
    assert 'button.setAttribute("aria-expanded", String(!compact));' in shell
    assert 'aria-controls="service-filter-advanced"' in shell
    assert entry.index("installServiceDiagnostics();") < entry.rindex(
        "installGlobalServiceFilter();",
    )


def test_web_design_guidelines_search_and_disclosure() -> None:
    """Search is named; mobile disclosure keeps focus and touch support."""
    ui = (ROOT / "nabla" / "api" / "ui.py").read_text(encoding="utf-8")
    css = (ASSETS / "api-diagnostics-ux.css").read_text(encoding="utf-8")
    shell = (ASSETS / "api-global-service-filter.js").read_text(encoding="utf-8")
    engine = (ASSETS / "api-service-filter.js").read_text(encoding="utf-8")

    assert 'id="service-filter" name="service-filter"' in ui
    assert 'enterkeyhint="search"' in ui
    assert "touch-action: manipulation;" in css
    assert "safe-area-inset-left" in css
    assert "text-wrap: balance;" in css
    assert 'button.setAttribute("aria-label",' in shell
    assert 'host.dataset.mobileExpanded = "true";' in shell
    assert "const compact = mobile" in shell
    assert 'input.closest("[hidden]")' in engine
