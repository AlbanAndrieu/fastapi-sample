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
    bootstrap = client.get("/api/assets/api-health.js")
    health = client.get("/api/assets/api-health-core.js")
    sickz = client.get("/api/assets/api-sickz.js")
    styles = client.get("/api/assets/api.css")

    assert page.status_code == 200
    assert 'href="/api/assets/api.css"' in page.text
    assert 'type="module" src="/api/assets/api-health.js"' in page.text
    assert "function computeOverall" not in page.text

    for asset in (bootstrap, health, sickz):
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]

    assert 'from "./api-health-core.js"' in bootstrap.text
    assert 'from "./api-sickz.js"' in bootstrap.text
    assert "function computeOverall" in health.text
    assert "function computeOverall" in sickz.text

    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]
    assert ".health-board" in styles.text


def test_health_board_platform_order_is_asset_contract() -> None:
    script = (_ASSET_DIR / "api-health-core.js").read_text(encoding="utf-8")

    priority_start = script.index("const first = [")
    priority_end = script.index("];", priority_start)
    priority = script[priority_start:priority_end]
    order = [
        priority.index('"albandrieu_truenas"'),
        priority.index('"cloudflare"'),
        priority.index('"pfsense"'),
        priority.index('"litellm"'),
        priority.index('"sentry"'),
        priority.index('"logfire"'),
    ]
    assert order == sorted(order)

    mandatory_start = script.index("export const MANDATORY = new Set([")
    mandatory_end = script.index("]);", mandatory_start)
    mandatory = script[mandatory_start:mandatory_end]
    assert '"albandrieu_truenas"' not in mandatory
    assert '"cloudflare"' not in mandatory
    assert '"pfsense"' not in mandatory
    assert '"logfire"' not in mandatory


def test_platform_labels_are_owned_by_health_module() -> None:
    script = (_ASSET_DIR / "api-health-core.js").read_text(encoding="utf-8")

    assert 'cloudflare: "Cloudflare Tunnels"' in script
    assert 'pfsense: "pfSense API"' in script
    assert 'logfire: "Pydantic Logfire"' in script


def test_health_bootstrap_stays_small() -> None:
    bootstrap = (_ASSET_DIR / "api-health.js").read_text(encoding="utf-8")

    assert len(bootstrap.splitlines()) < 50
    assert "loadHealthBoards" in bootstrap
    assert "computeOverall" not in bootstrap


def test_optional_runtime_clients_are_installed() -> None:
    assert import_module("cloudflare").Cloudflare is not None
    assert import_module("truenas_api_client").Client is not None
