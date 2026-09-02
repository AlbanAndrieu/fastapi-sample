"""Contracts for the grouped health/exposure UI assets."""

from pathlib import Path

from nabla.api.ui import render_api_root_page


ASSETS = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_api_page_orders_core_truenas_groups_then_exposure() -> None:
    html = render_api_root_page(title_suffix="test", app_version="test")

    core = html.index('id="health-core-group-heading"')
    truenas = html.index('id="truenas-platform"')
    groups = html.index('id="health-services-groups"')
    exposure = html.index('id="sickz-board-title"')
    assert core < truenas < groups < exposure
    assert 'id="service-filter"' in html
    assert 'id="service-expand-issues"' in html
    assert 'id="service-collapse-all"' in html


def test_service_group_asset_mirrors_site_criticality_contract() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")

    for label in (
        "1 · Infrastructure foundations",
        "2 · Shared data & state",
        "3 · Shared platform services",
        "4 · Applications & consumers",
        "5 · Support / low blast radius",
    ):
        assert label in source
    for relation in (
        "dependsOn",
        "consumesApi",
        "routesTo",
        "storesIn",
        "authenticatesVia",
        "partOf",
    ):
        assert relation in source
    assert 'document.createElement("details")' in source
    assert "section.open = issueCount > 0" in source


def test_true_nas_is_not_duplicated_in_generic_health_rows() -> None:
    source = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")

    assert 'key !== "truenas_api"' in source
    assert 'key !== "albandrieu_truenas"' in source
    assert "truenasApiCheck" not in source
