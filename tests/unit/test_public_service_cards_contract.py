"""Public discovery cards are not fabricated operational evidence."""

from pathlib import Path

from nabla.api.catalog_routes import routes_from_catalog
from nabla.api.site_architecture_catalog import load_catalog_snapshot

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla/api/assets"


def test_gatus_and_garage_webui_have_explicit_discovery_labels() -> None:
    source = (ASSETS / "api-health-garage.js").read_text(encoding="utf-8")
    assert '["gatus", "Gatus"]' in source
    assert '["garage-webui", "Garage Web UI"]' in source
    assert "homelab?.public_card_candidates" in source
    assert 'state: "unknown"' in source
    assert "reachable: null" in source
    assert "Object.hasOwn(projected, id)" in source
    assert "no current independent probe evidence" in source


def test_gatus_catalog_and_private_garage_boundary() -> None:
    routes = {item.service_id: item for item in routes_from_catalog(load_catalog_snapshot())}
    assert routes["gatus"].entity_ref == "component:default/gatus"
    assert routes["gatus"].public is True
    assert routes["garage"].public is False
    assert routes["garage-admin"].public is False
