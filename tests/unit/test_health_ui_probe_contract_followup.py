"""Contracts for the post-1.20.3 probe-grid and catalog follow-up."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from nabla.api.catalog_routes import routes_from_catalog
from nabla.api.site_architecture_catalog import load_catalog_snapshot
from tests.unit.catalog_v2_fixture import service as v2_service

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"

# Request-path order since #370: network, edge, then service evidence.
PROBE_KINDS = (
    "dns",
    "tcp",
    "tls",
    "http",
    "cloudflare",
    "access",
    "service-token",
    "api",
    "websocket",
    "metrics",
    "policy",
)


def test_probe_grid_pins_one_canonical_column_per_evidence_kind() -> None:
    source = (ASSETS / "api-health-ui-probe-grid.js").read_text(encoding="utf-8")

    positions = [source.index(f'["{kind}",') for kind in PROBE_KINDS]
    assert positions == sorted(positions)
    assert "export const PROBE_COLUMNS" in source
    assert "cell.dataset.probeColumn" in source
    assert "cell.style.gridColumn" in source
    # #370 exposes the grid as a list; aria-colcount is invalid on role=list.
    assert 'grid.setAttribute("role", "list")' in source
    assert 'cell.setAttribute("role", "listitem")' in source
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


def test_secure_int_hostname_requires_cloudflare_access() -> None:
    service = v2_service("joplin", "https://joplin.int.albandrieu.com", public=True)

    assert service.access_required is True
    assert service.public_https_probe_url == "https://joplin.int.albandrieu.com/"

    with pytest.raises(ValidationError, match="cannot disable Cloudflare Access"):
        v2_service("joplin", "https://joplin.int.albandrieu.com", public=True, access=False)


def test_packaged_snapshot_keeps_public_exposure_baseline() -> None:
    by_id = {item.service_id: item for item in routes_from_catalog(load_catalog_snapshot())}

    for service_id in ("prometheus", "grafana", "gatus", "affine", "freshrss", "clickhouse", "scrutiny"):
        assert by_id[service_id].public is True
        assert by_id[service_id].access_required is True

    joplin = by_id["joplin"]
    assert (joplin.backend_host, joplin.backend_port) == ("172.17.0.24", 22300)
    # Owner decision 10/11: Joplin sync clients cannot pass an Access login.
    assert (joplin.public, joplin.access_required) == (True, False)
