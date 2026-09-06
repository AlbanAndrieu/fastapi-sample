"""Contracts for the grouped health/exposure UI assets."""

from pathlib import Path

from nabla.api.ui import render_api_root_page


ASSETS = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_api_page_prioritizes_service_groups_before_core_drilldown() -> None:
    html = render_api_root_page(title_suffix="test", app_version="test")

    overview = html.index('id="service-health-overview"')
    groups = html.index('id="health-services-groups"')
    truenas = html.index('id="truenas-platform"')
    exposure = html.index('id="sickz-board-title"')
    assert overview < groups < truenas < exposure
    assert 'id="service-filter"' in html
    assert 'id="service-expand-issues"' in html
    assert 'id="service-collapse-all"' in html


def test_service_group_asset_mirrors_site_criticality_contract() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    classification = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    for label in (
        "1 · Services & experiments",
        "2 · Critical core platform",
        "3 · Security controls",
        "4 · Shared platform & data",
        "5 · Observability & support",
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
        assert relation in classification
    assert 'document.createElement("details")' in source
    assert "openWhenHealthy" in source
    assert "service-health-overview" in source
    assert "CRITICALITY_WEIGHT" in source


def test_true_nas_keeps_summary_row_and_separate_api_drilldown() -> None:
    source = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")
    page = render_api_root_page(title_suffix="test", app_version="test")

    assert 'key !== "truenas_api"' in source
    assert 'key !== "albandrieu_truenas"' not in source
    assert "truenasApiCheck" not in source
    assert "Core drill-down · TrueNAS platform" in page


def test_service_classification_supports_explicit_role_and_criticality() -> None:
    source = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    assert "presentationRole" in source
    assert "criticality" in source
    for foundation in ("truenas", "docker", "pfsense", "talos", "kubernetes", "etcd"):
        assert f'"{foundation}"' in source
    for value in ("critical", "high", "medium", "low"):
        assert f'"{value}"' in source


def test_service_health_ui_exposes_semantic_status_badges() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    css = (ASSETS / "api-service-groups.css").read_text(encoding="utf-8")

    for label in ("Operational", "Degraded", "HTTP issue", "Unknown", "Down"):
        assert f'"{label}"' in source
    assert "health-meta-badge--critical" in css
    assert "health-meta-badge--impact" in css
    assert "transitiveDependents" in source
    assert "downstream" in source
    assert "service-health-overview" in css
