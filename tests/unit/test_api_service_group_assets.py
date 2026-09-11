"""Contracts for the grouped health/exposure UI assets."""

from pathlib import Path

from nabla.api.ui import render_api_root_page


ASSETS = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_api_page_prioritizes_service_board_before_technical_drilldowns() -> None:
    html = render_api_root_page(
        title_suffix="test",
        app_version="test",
        runtime_mode="fastapi_cloud",
    )

    hero = html.index('class="hero-code"')
    truenas = html.index('id="truenas-platform"')
    runtime = html.index('id="runtime-topology"')
    health = html.index('id="health-board"')
    overview = html.index('id="service-health-overview"')
    groups = html.index('id="health-services-groups"')
    exposure = html.index('id="sickz-board-title"')
    assert hero < health < overview < groups < exposure < truenas < runtime
    assert "Core drill-down · TrueNAS platform + API" in html
    assert "FastAPI Cloud runtime" in html
    assert 'id="service-filter"' in html
    assert 'id="service-expand-issues"' in html
    assert 'id="service-collapse-all"' in html


def test_service_group_asset_mirrors_site_criticality_contract() -> None:
    source = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    classification = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    for label in (
        "1 · Critical core platform",
        "2 · Services & experiments",
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
        encoding="utf-8",
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
    assert "Core drill-down · TrueNAS platform + API" in page


def test_service_classification_supports_explicit_role_and_criticality() -> None:
    source = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    assert "presentationRole" in source
    assert "criticality" in source
    for foundation in ("truenas", "docker", "pfsense", "talos", "kubernetes", "etcd"):
        assert f'"{foundation}"' in source
    for value in ("critical", "high", "medium", "low"):
        assert f'"{value}"' in source


def test_grouping_uses_canonical_topology_metadata_without_id_overrides() -> None:
    source = (ASSETS / "api-service-classification.js").read_text(encoding="utf-8")

    assert "PRESENTATION_GROUP_OVERRIDES" not in source
    presentation_group = source.split("function presentationGroup", maxsplit=1)[1]

    security = presentation_group.index('node?.category === "security"')
    critical = presentation_group.index(
        'if (criticality === "critical") return "core-critical";',
    )
    explicit_support = presentation_group.index(
        'if (explicitRole === "support") return "support";',
    )
    observability = presentation_group.index("OBSERVABILITY_KINDS.has(node.kind)")
    shared_core = presentation_group.index('return "shared-core";')

    assert security < critical
    assert "!FOUNDATION_IDS.has(node.id)" in presentation_group
    assert explicit_support < shared_core
    assert observability < shared_core
    assert "Canonical nabla-compose metadata decides presentation" in source


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


def test_critical_core_group_is_first() -> None:
    javascript = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")

    core = javascript.index('label: "1 · Critical core platform"')
    services = javascript.index('label: "2 · Services & experiments"')
    assert core < services


def test_health_grouping_reuses_shared_topology_loader() -> None:
    groups = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")
    loader = (ASSETS / "api-topology-data.js").read_text(encoding="utf-8")

    assert 'from "./api-topology-data.js"' in groups
    assert "await fetchTopology()" in groups
    assert 'fetchJson("/api/homelab-topology")' in loader
    assert 'fetchJson("/api/homelab/declared-services")' in loader
    assert "topologyFromDeclaredServices" in loader
    assert 'source: "declared-services-fallback"' in loader
    assert "presentationRole" in loader
    assert "securityFunctions" in loader
    assert "classification-unavailable" in loader
    assert "Service classification" in groups
    assert "Topology and declared-service catalog could not be loaded" in groups


def test_health_board_renders_merged_homelab_evidence_once() -> None:
    health = (ASSETS / "api-health-core.js").read_text(encoding="utf-8")

    assert "const merged = homelab ? mergeHomelabEvidence(data, homelab) : data;" in health
    assert "render(merged, snapshot.platform_metrics);" in health
    assert "render(data, snapshot.platform_metrics);" not in health
    assert health.count("mergeHomelabEvidence(data, homelab)") == 1


def test_service_overview_omits_empty_operational_counters() -> None:
    groups = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")

    assert 'if (total === 0) return "";' in groups
    assert 'overviewCard("Other / optional", buckets.get("external") || [])' in groups
    assert "No classified rows" in groups


def test_sickz_keeps_one_exposure_section_without_duplicate_service_groups() -> None:
    groups = (ASSETS / "api-service-groups.js").read_text(encoding="utf-8")

    start = groups.index("export async function organizeSickzRows")
    sickz = groups[start:]

    assert "serviceGroupSection(" not in sickz
    assert 'document.createElement("details")' not in sickz
    assert "sortRows(groupRows)" in sickz
    assert groups.count('label: "External / optional integrations"') == 1
    assert "installServiceFilter" not in groups
    assert "activeFilter" not in groups


def test_sickz_labels_truenas_as_https_exposure_not_api_health() -> None:
    source = (ASSETS / "api-sickz.js").read_text(encoding="utf-8")

    assert "TrueNAS HTTPS listener · exposure policy" in source
    assert "This is not the authenticated TrueNAS API probe" in source
    assert "Core drill-down · TrueNAS platform + API" in source
