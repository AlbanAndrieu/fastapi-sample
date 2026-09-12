"""Contracts for the post-1.20.3 probe-grid and catalog follow-up."""

from pathlib import Path

import pytest

from nabla.api import homelab_catalog
from nabla.api.homelab_models import HomelabService

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"

PROBE_KINDS = (
    "dns",
    "http",
    "tls",
    "cloudflare",
    "access",
    "service-token",
    "api",
    "policy",
    "tcp",
    "websocket",
    "metrics",
)


def test_probe_grid_pins_one_canonical_column_per_evidence_kind() -> None:
    source = (ASSETS / "api-health-ui-probe-grid.js").read_text(encoding="utf-8")

    positions = [source.index(f'["{kind}",') for kind in PROBE_KINDS]
    assert positions == sorted(positions)
    assert "export const PROBE_COLUMNS" in source
    assert "cell.dataset.probeColumn" in source
    assert "cell.style.gridColumn" in source
    assert 'setAttribute("aria-colcount", String(PROBE_COLUMNS.length))' in source
    assert 'return "neutral"' in source


def test_probe_drawer_keeps_the_same_eleven_columns_at_all_breakpoints() -> None:
    stylesheet = (ASSETS / "api-health-ui-final-followup.css").read_text(
        encoding="utf-8",
    )

    assert "grid-template-columns: repeat(11, minmax(4.6rem, 1fr));" in stylesheet
    assert "grid-template-columns: repeat(11, minmax(9rem, 1fr));" in stylesheet
    assert "grid-template-columns: repeat(11, minmax(7rem, 1fr));" in stylesheet
    assert "overflow-x: auto;" in stylesheet
    assert "grid-template-columns: 1fr;" not in stylesheet


def test_cloudflare_access_diagnostics_use_backend_project_selection() -> None:
    source = (ASSETS / "api-health-ui-consistency-followup.js").read_text(
        encoding="utf-8",
    )

    assert "family?.selection" in source
    assert "PROJECT_ACCESS_POLICY" not in source
    assert "PROJECT_SERVICE_AUTH" not in source
    assert r"application\(s\) visible" in source
    assert r"policy object\(s\) visible" in source
    assert r"service token\(s\) visible" in source


def test_secure_int_hostname_requires_explicit_cloudflare_edge_classification() -> None:
    service = HomelabService.model_validate(
        {
            "id": "joplin",
            "name": "Joplin",
            "external": True,
            "tunnelUrl": "https://joplin.int.albandrieu.com",
            "tunnelSecure": True,
        },
    )

    assert service.effective_cloudflare_access_required is True
    assert service.public_https_probe_url == "https://joplin.int.albandrieu.com/"

    with pytest.raises(ValidationError, match="cannot disable Cloudflare Access"):
        HomelabService.model_validate(
            {
                "id": "joplin",
                "name": "Joplin",
                "external": True,
                "tunnelUrl": "https://joplin.int.albandrieu.com",
                "tunnelSecure": True,
                "cloudflareAccessRequired": False,
            },
        )


def test_packaged_catalog_matches_nabla_compose_197_exposure_baseline() -> None:
    homelab_catalog.clear_homelab_catalog_cache()
    try:
        catalog = homelab_catalog._load_bootstrap_catalog()
        by_name = {service.name: service for service in catalog.services}

        for name in (
            "AdGuard Home",
            "Prometheus",
            "Uptime Kuma",
            "Grafana",
            "Gatus",
            "Affine",
            "FreshRSS",
            "Clickhouse",
        ):
            assert by_name[name].external is True

        joplin = by_name["Joplin"]
        assert joplin.service_id == "joplin"
        assert joplin.internal_host == "172.17.0.24"
        assert joplin.internal_port == 22300
        assert joplin.external is True
        assert joplin.effective_cloudflare_access_required is True

        scrutiny = by_name["Scrutiny"]
        assert scrutiny.external is True
        assert scrutiny.effective_cloudflare_access_required is True
    finally:
        homelab_catalog.clear_homelab_catalog_cache()
