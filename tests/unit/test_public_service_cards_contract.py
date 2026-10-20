"""Public discovery cards are not fabricated operational evidence."""

import json
from pathlib import Path

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
    catalog = json.loads(
        (ROOT / "nabla/api/data/homelab-services.json").read_text(
            encoding="utf-8",
        ),
    )
    services = catalog["services"]
    gatus = [row for row in services if row.get("id") == "gatus"]
    assert len(gatus) == 1
    assert gatus[0]["name"] == "Gatus"
    assert gatus[0]["external"] is True
    private = {row["id"] for row in services if row.get("id") in {"garage", "garage-admin"}}
    assert private == {"garage", "garage-admin"}
