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


def test_security_group_exposes_nist_csf_2_reference() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    classification = (ASSETS / "api-service-classification.js").read_text(
        encoding="utf-8"
    )
    css = (ASSETS / "api-service-groups.css").read_text(encoding="utf-8")

    assert "NIST Cybersecurity Framework (CSF) 2.0" in source
    assert "https://doi.org/10.6028/NIST.CSWP.29" in source
    for key, label in (
        ("govern", "Govern"),
        ("identify", "Identify"),
        ("protect", "Protect"),
        ("detect", "Detect"),
        ("respond", "Respond"),
        ("recover", "Recover"),
    ):
        assert f'key: "{key}"' in classification
        assert f'label: "{label}"' in classification
    assert "securityFunctions" in classification
    assert "security-controls" in classification
    assert "health-meta-badge--security-function" in css
    assert "security-framework-function--declared" in css


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


def test_structural_hosting_affects_blast_radius_not_functional_dependency() -> None:
    source = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    assert '"hostedBy"' in source
    assert "IMPACT_RELATION_TYPES" in source
    assert "FUNCTIONAL_RELATION_TYPES" in source
    functional_block = source.split(
        "const FUNCTIONAL_RELATION_TYPES",
        maxsplit=1,
    )[1].split("]);", maxsplit=1)[0]
    assert '"hostedBy"' not in functional_block


def test_service_outcome_can_remain_operational_while_at_risk() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    css = (ASSETS / "api-service-groups.css").read_text(encoding="utf-8")

    assert 'return "At risk"' in source
    assert "rowOutcomeOperational" in source
    assert 'row.dataset.semanticStatus === "at-risk"' in source
    assert "probeLatencyMs" in source
    assert 'addBadge(tags, `${latency} ms`, "metric")' in source
    assert "health-meta-badge--status-at-risk" in css
    assert "health-meta-badge--metric" in css


def test_service_health_ui_exposes_semantic_status_badges() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    css = (ASSETS / "api-service-groups.css").read_text(encoding="utf-8")

    for label in ("Operational", "At risk", "Degraded", "Unknown", "Down"):
        assert f'"{label}"' in source
    assert '"HTTP issue"' not in source
    assert "health-meta-badge--critical" in css
    assert "health-meta-badge--impact" in css
    assert "transitiveDependents" in source
    assert "downstream" in source
    assert "downstreamCount" in source
    assert "Number(right.dataset.downstreamCount" in source
    assert "service-health-overview" in css


def test_service_overview_surfaces_bounded_platform_metrics() -> None:
    groups = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    health = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")

    assert "platformOverviewDetails" in groups
    assert "truenas_memory_available_ratio" in groups
    assert "truenas_cpu_busy_ratio" in groups
    assert "telemetry_total" in groups
    assert "pfsense_metrics_up" in groups
    assert "Prometheus metrics not configured" in groups
    assert "Prometheus telemetry unavailable" in groups
    assert "snapshot.platform_metrics" in health
