"""Regression tests for the external API landing-page assets."""

from importlib import import_module
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.routes import register_routes


_ASSET_DIR = Path(__file__).parents[2] / "nabla" / "api" / "assets"


def test_api_page_serves_external_assets() -> None:
    app = FastAPI(version="test-version")
    register_routes(app)
    client = TestClient(app)

    page = client.get("/api")
    script = client.get("/api/assets/api-health.js")
    styles = client.get("/api/assets/api.css")

    assert page.status_code == 200
    assert 'href="/api/assets/api.css"' in page.text
    assert 'src="/api/assets/api-health.js"' in page.text
    assert "function computeOverall" not in page.text
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "function computeOverall" in script.text
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]
    assert ".health-board" in styles.text


def test_health_board_platform_order_is_asset_contract() -> None:
    script = (_ASSET_DIR / "api-health.js").read_text(encoding="utf-8")

    order = [
        script.index('"albandrieu_truenas"'),
        script.index('"cloudflare"'),
        script.index('"pfsense"'),
        script.index('"litellm"'),
        script.index('"sentry"'),
        script.index('"logfire"'),
    ]
    assert order == sorted(order)

    mandatory_start = script.index("const MANDATORY = new Set([")
    mandatory_end = script.index("]);", mandatory_start)
    mandatory = script[mandatory_start:mandatory_end]
    assert '"albandrieu_truenas"' not in mandatory
    assert '"cloudflare"' not in mandatory
    assert '"pfsense"' not in mandatory
    assert '"logfire"' not in mandatory


def test_platform_labels_are_owned_by_static_asset() -> None:
    script = (_ASSET_DIR / "api-health.js").read_text(encoding="utf-8")

    assert 'cloudflare: "Cloudflare Tunnels"' in script
    assert 'pfsense: "pfSense API"' in script
    assert 'logfire: "Pydantic Logfire"' in script


def test_optional_runtime_clients_are_installed() -> None:
    assert import_module("cloudflare").Cloudflare is not None
    assert import_module("truenas_api_client").Client is not None
