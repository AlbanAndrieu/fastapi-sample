"""Contracts for the health-board operator navigation and refresh delta UX."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_entrypoint_installs_operator_ux_before_refresh_controller() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-health-operator-ux.js"' in entrypoint
    operator = entrypoint.index("installHealthOperatorUx();")
    controller = entrypoint.index("installHealthBoardController();")
    assert operator < controller


def test_operator_navigation_targets_existing_health_sections() -> None:
    source = (ASSETS / "api-health-operator-ux.js").read_text(encoding="utf-8")

    for target in (
        "health-board",
        "sickz-board-title",
        "truenas-platform",
        "runtime-topology",
    ):
        assert f'id: "{target}"' in source
    assert 'id = "service-section-navigation"' in source
    assert 'className = "service-filter-health-summary"' in source
    assert 'className = "service-filter-health-chip"' in source
    assert "scrollIntoView" in source
    assert "prefers-reduced-motion: reduce" in source


def test_operator_navigation_counters_follow_visible_service_rows() -> None:
    source = (ASSETS / "api-health-operator-ux.js").read_text(encoding="utf-8")

    assert "function visibleRatio(selector)" in source
    assert "rows.filter((row) => !row.hidden).length" in source
    assert "#health-checks > [data-service-filter-target]" in source
    assert "#health-services-groups [data-service-filter-target]" in source
    assert "#sickz-checks > [data-service-filter-target]" in source
    assert "#truenas-probe-list .truenas-probe-row" in source
    assert 'getElementById("runtime-instance-count")' in source
    assert '"service-filter-changed"' in source
    assert "scheduleNavigationRefresh," in source


def test_refresh_controller_announces_only_completed_snapshot_cycles() -> None:
    controller = (ASSETS / "api-health-controller.js").read_text(encoding="utf-8")

    assert "function announceRefreshComplete(" in controller
    assert 'new CustomEvent("health-board-refreshed"' in controller
    assert "forceRefresh," in controller
    assert "includeTechnical," in controller
    assert "refreshing: snapshot?.refreshing === true" in controller
    decorate = controller.index("decorateProbeTelemetry(snapshot);")
    announce = controller.index(
        "announceRefreshComplete(snapshot, { forceRefresh, includeTechnical });",
        decorate,
    )
    assert decorate < announce


def test_refresh_delta_tracks_regressions_and_recoveries_without_unknown_noise() -> None:
    source = (ASSETS / "api-health-operator-ux.js").read_text(encoding="utf-8")

    assert 'new Set(["at-risk", "degraded", "down"])' in source
    assert 'previous === "unknown" || current === "unknown"' in source
    assert 'return "recovered";' in source
    assert 'return "regressed";' in source
    assert "value.row.dataset.healthChange = kind;" in source
    assert 'document.addEventListener("health-board-refreshed"' in source
    assert "baselineStatuses === null" in source


def test_refresh_delta_summary_reuses_existing_filter_chip_presentation() -> None:
    source = (ASSETS / "api-health-operator-ux.js").read_text(encoding="utf-8")

    assert 'summary.id = "service-health-changes"' in source
    assert 'summary.className = "service-filter-active"' in source
    assert 'button.className = "service-filter-active-chip"' in source
    assert 'summary.setAttribute("aria-live", "polite")' in source
    assert 'focusFirstChange("' not in source
    assert "focusFirstChange(kind)" in source
