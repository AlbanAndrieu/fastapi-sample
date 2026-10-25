"""Contracts for the health-board service detail drawer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_health_entrypoint_installs_service_detail_drawer() -> None:
    entrypoint = (ASSETS / "api-health.js").read_text(encoding="utf-8")

    assert 'from "./api-service-detail-drawer.js"' in entrypoint
    diagnostics = entrypoint.index("installServiceDiagnostics();")
    drawer = entrypoint.index("installServiceDetailDrawer();")
    controller = entrypoint.index("installHealthBoardController();")
    assert diagnostics < drawer < controller


def test_detail_drawer_reuses_existing_row_metadata_and_probe_evidence() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")

    direct_dataset_fields = (
        "serviceKey",
        "serviceUrl",
        "presentationGroup",
        "environments",
        "exposureScope",
        "exposureMode",
        "exposurePolicy",
        "healthChange",
    )
    for dataset_field in direct_dataset_fields:
        assert f"dataset.{dataset_field}" in source
    assert "dataset?.serviceName" in source
    assert "dataset?.semanticStatus" in source
    assert 'row.querySelectorAll(".service-probe")' in source
    assert 'probe.getAttribute("aria-label") || probe.title' in source
    assert "data-service-filter-target" in source


def test_detail_drawer_links_only_to_http_or_https_targets() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")

    assert "function safeHttpUrl(value)" in source
    assert '["http:", "https:"].includes(url.protocol)' in source
    assert 'link.target = "_blank";' in source
    assert 'link.rel = "noopener noreferrer";' in source


def test_detail_drawer_is_accessible_and_restores_focus() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")

    assert 'drawer.setAttribute("role", "dialog")' in source
    assert 'drawer.setAttribute("aria-modal", "false")' in source
    assert 'drawer.setAttribute("aria-labelledby", "service-detail-title")' in source
    assert 'trigger.setAttribute("aria-haspopup", "dialog")' in source
    assert 'event.key === "Escape"' in source
    assert "trigger.focus({ preventScroll: true })" in source


def test_detail_drawer_refreshes_without_new_health_engine() -> None:
    source = (ASSETS / "api-service-detail-drawer.js").read_text(encoding="utf-8")

    assert 'document.addEventListener("service-filter-changed", scheduleActiveRefresh)' in source
    assert 'document.addEventListener("health-board-refreshed", scheduleActiveRefresh)' in source
    assert "new MutationObserver" in source
    assert "fetch(" not in source
    # The drawer reuses the bounded cached board snapshot; no direct per-card fetch.
    assert 'fetchHealthBoard()' in source
    assert "window.fetch(" not in source


def test_detail_drawer_has_dedicated_responsive_stylesheet() -> None:
    stylesheet = (ASSETS / "api.css").read_text(encoding="utf-8")
    drawer_css = (ASSETS / "api-service-detail-drawer.css").read_text(encoding="utf-8")

    assert '@import url("./api-service-detail-drawer.css");' in stylesheet
    assert ".service-detail-drawer" in drawer_css
    assert "position: fixed" in drawer_css
    assert ".service-detail-trigger" in drawer_css
    assert '[data-detail-selected="true"]' in drawer_css
    assert "@media (max-width: 720px)" in drawer_css


def test_gatus_drawer_distinguishes_down_up_and_missing_observations() -> None:
    drawer = (ASSETS / "api-service-detail-drawer.js").read_text(
        encoding="utf-8"
    )
    coverage = (ASSETS / "api-service-gatus-coverage.js").read_text(
        encoding="utf-8"
    )
    assert "Failing checks" in drawer
    assert "Checks without usable samples" in drawer
    assert "Successful checks" in drawer
    assert 'summary.missing.push(' in coverage
    assert 'summary.successes.push(' in coverage
    assert "linkedCatalogueItem(" in drawer
    assert "Unlisted catalogue services have unknown Gatus coverage" in drawer
    assert "not run" in drawer
