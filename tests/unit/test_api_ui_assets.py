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
    ui = client.get("/api/assets/api-health-ui.js")
    sickz = client.get("/api/assets/api-sickz.js")
    styles = client.get("/api/assets/api.css")
    base_styles = client.get("/api/assets/api-base.css")
    health_styles = client.get("/api/assets/api-health.css")
    sickz_styles = client.get("/api/assets/api-sickz.css")

    assert page.status_code == 200
    assert 'href="/api/assets/api.css"' in page.text
    assert 'type="module" src="/api/assets/api-health.js"' in page.text
    assert "function computeOverall" not in page.text

    for asset in (bootstrap, health, ui, sickz):
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]

    assert 'from "./api-health-core.js"' in bootstrap.text
    assert 'from "./api-sickz.js"' in bootstrap.text
    assert 'from "./api-health-ui.js"' in health.text
    assert 'from "./api-health-ui.js"' in sickz.text
    assert 'from "./api-health-core.js"' not in sickz.text
    assert "function computeOverall" in health.text
    assert "function computeOverall" in sickz.text

    for asset in (styles, base_styles, health_styles, sickz_styles):
        assert asset.status_code == 200
        assert "text/css" in asset.headers["content-type"]

    assert '@import url("./api-base.css")' in styles.text
    assert '@import url("./api-health.css")' in styles.text
    assert '@import url("./api-sickz.css")' in styles.text
    assert "body {" in base_styles.text
    assert ".health-board" in health_styles.text
    assert ".sickz-pfsense-port" in sickz_styles.text


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


def test_health_assets_stay_within_refactoring_thresholds() -> None:
    bootstrap = (_ASSET_DIR / "api-health.js").read_text(encoding="utf-8")
    health = (_ASSET_DIR / "api-health-core.js").read_text(encoding="utf-8")
    ui = (_ASSET_DIR / "api-health-ui.js").read_text(encoding="utf-8")
    sickz = (_ASSET_DIR / "api-sickz.js").read_text(encoding="utf-8")

    assert len(bootstrap.splitlines()) < 50
    assert len(health.splitlines()) < 400
    assert len(ui.splitlines()) < 250
    assert len(sickz.splitlines()) < 400
    assert "loadHealthBoards" in bootstrap
    assert "computeOverall" not in bootstrap


def test_api_style_assets_stay_below_review_threshold() -> None:
    entrypoint = (_ASSET_DIR / "api.css").read_text(encoding="utf-8")
    base = (_ASSET_DIR / "api-base.css").read_text(encoding="utf-8")
    health = (_ASSET_DIR / "api-health.css").read_text(encoding="utf-8")
    sickz = (_ASSET_DIR / "api-sickz.css").read_text(encoding="utf-8")

    assert len(entrypoint.splitlines()) < 20
    assert len(base.splitlines()) < 400
    assert len(health.splitlines()) < 400
    assert len(sickz.splitlines()) < 250


def test_optional_runtime_clients_are_installed() -> None:
    assert import_module("cloudflare").Cloudflare is not None
    assert import_module("truenas_api_client").Client is not None
