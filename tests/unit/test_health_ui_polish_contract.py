"""Static contracts for the health-board operator polish layer."""

from pathlib import Path


ASSETS = Path("nabla/api/assets")


def test_health_ui_polish_is_wired_into_the_api_page() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'import { installHealthUiPolish } from "./api-health-ui-polish.js";' in entrypoint
    assert entrypoint.count("installHealthUiPolish();") == 1
    assert '@import url("./api-health-ui-polish.css");' in stylesheet


def test_health_legend_combines_status_tiers_and_probe_meanings() -> None:
    javascript = (ASSETS / "api-health-ui-polish.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-health-ui-polish.css").read_text(encoding="utf-8")

    assert "details.open = true" in javascript
    assert "Legend · health, tiers & probe evidence" in javascript
    assert "Required infra (albandrieu.com)" in javascript
    assert "Required health check" in javascript
    assert "Optional health check" in javascript
    assert "Evidence colors" in javascript
    assert "Cloudflare Tunnel" in javascript
    assert "Service Token" in javascript
    assert "Prometheus / metrics" in javascript
    assert ".health-legend--green i" in stylesheet
    assert ".health-legend--amber i" in stylesheet
    assert ".health-legend--red i" in stylesheet
    assert ".health-legend--gray i" in stylesheet


def test_desktop_filter_rail_and_probe_timing_are_stable_and_responsive() -> None:
    javascript = (ASSETS / "api-health-ui-polish.js").read_text(encoding="utf-8")
    stylesheet = (ASSETS / "api-health-ui-polish.css").read_text(encoding="utf-8")

    assert 'layout.className = "service-health-layout"' in javascript
    assert 'column.className = "health-probe-timing-column"' in javascript
    assert ".service-health-layout" in stylesheet
    assert "grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);" in stylesheet
    assert "@media (max-width: 1120px)" in stylesheet
    assert ".health-probe-timing-column .health-meta-badge--probing" in stylesheet
    assert "animation: none;" in stylesheet
    assert "font-variant-numeric: tabular-nums;" in stylesheet
    assert ".service-overview-card" in stylesheet
    assert "height: 5.65rem;" in stylesheet


def test_pfsense_is_required_and_service_help_uses_canonical_topology() -> None:
    javascript = (ASSETS / "api-health-ui-polish.js").read_text(encoding="utf-8")

    assert 'const PFSENSE_KEY = "pfsense";' in javascript
    assert "MANDATORY.add(PFSENSE_KEY);" in javascript
    assert "fetchTopology()" in javascript
    assert "node?.description" in javascript
    assert 'help.className = "service-description-help"' in javascript


def test_python_ci_keeps_success_output_short_and_failure_output_actionable() -> None:
    workflow = Path(".github/workflows/python.yml").read_text(encoding="utf-8")

    assert "--tb=short" in workflow
    assert ">pytest.log 2>&1" in workflow
    assert 'echo "::group::pytest failure · last 180 lines"' in workflow
    assert "tail -n 180 pytest.log" in workflow
    assert 'summary="$(tail -n 1 pytest.log)"' in workflow
    assert '>>"${GITHUB_STEP_SUMMARY}"' in workflow
