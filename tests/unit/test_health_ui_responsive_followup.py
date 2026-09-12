"""Static contracts for the service diagnostics responsive follow-up."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_followup_assets_are_loaded_after_base_health_ui() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'from "./api-health-ui-responsive-followup.js"' in entrypoint
    assert 'from "./api-health-ui-probe-explanations.js"' in entrypoint
    assert entrypoint.index("installHealthUiResponsiveFollowup();") > entrypoint.index(
        "installPlatformFlowUi();",
    )
    assert entrypoint.index("installHealthUiProbeExplanations();") > entrypoint.index(
        "installServiceProbePlanes();",
    )
    assert '@import url("./api-health-ui-responsive-followup.css");' in stylesheet
    assert stylesheet.index(
        '@import url("./api-health-ui-responsive-followup.css");',
    ) < stylesheet.index('@import url("./api-health-ui-final-followup.css");')


def test_drawer_keeps_runtime_and_dependency_sections_stable() -> None:
    javascript = (ASSETS / "api-health-ui-responsive-followup.js").read_text(
        encoding="utf-8",
    )

    assert "DRAWER_SETTLE_MS" in javascript
    assert 'restoreSection(body, row, "runtime")' in javascript
    assert 'restoreSection(body, row, "dependencies")' in javascript
    assert "retainedDuringRefresh" in javascript
    assert "Current status reason" in javascript


def test_sickz_lan_skip_is_explained_without_duplicate_target_name() -> None:
    javascript = (ASSETS / "api-health-ui-responsive-followup.js").read_text(
        encoding="utf-8",
    )

    assert ("External exposure policy probe skipped from trusted LAN; LAN/TCP probes are independent.") in javascript
    assert "text.match(/\\s+Targets:" in javascript
    assert "targets.every((target) => names.has(target))" in javascript


def test_bounded_probe_tooltips_do_not_tell_enabled_lan_to_enable_itself() -> None:
    javascript = (ASSETS / "api-health-ui-probe-explanations.js").read_text(
        encoding="utf-8",
    )

    assert "internal_probes_enabled" in javascript
    assert "bounded rotating window" in javascript
    assert "unsampled service is not considered unreachable" in javascript
    assert "Runtime RUNNING and LAN/TCP reachability are independent signals" in javascript


def test_truenas_probe_first_note_is_neutralized_and_details_are_aligned() -> None:
    javascript = (ASSETS / "api-health-ui-responsive-followup.js").read_text(
        encoding="utf-8",
    )
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )

    assert "TrueNAS flow rendered from bounded /api/homelab/probes first" in javascript
    assert "truenas-platform-info" in javascript
    assert "information/freshness note, not an error" in javascript
    assert "#truenas-platform > .service-detail-trigger" in stylesheet


def test_workstation_filter_docks_from_local_browser_even_in_homelab_mode() -> None:
    javascript = (ASSETS / "api-health-ui-responsive-followup.js").read_text(
        encoding="utf-8",
    )

    assert "function isWorkstationBrowser()" in javascript
    assert 'window.location.port === "8080"' in javascript
    assert 'mode === "local" || isWorkstationBrowser()' in javascript
    assert '"fastapi-health-filter-docked-v2"' in javascript
    assert 'window.matchMedia("(min-width: 1121px)")' in javascript


def test_workstation_filter_touches_left_edge_and_overlaps_content_slightly() -> None:
    javascript = (ASSETS / "api-health-ui-responsive-followup.js").read_text(
        encoding="utf-8",
    )
    stylesheet = (ASSETS / "api-health-ui-responsive-followup.css").read_text(
        encoding="utf-8",
    )

    assert "ensureWorkstationDockStyles" in javascript
    assert "@media (min-width: 1121px)" in javascript
    assert "left: 0;" in javascript
    assert "width: 470px;" in javascript
    assert "max-width: 470px;" in javascript
    assert "margin-left: 450px;" in javascript
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in javascript
    assert "@media (min-width: 721px) and (max-width: 1100px)" in stylesheet
    assert "@media (max-width: 720px)" in stylesheet
    assert "@media (max-width: 480px)" in stylesheet
