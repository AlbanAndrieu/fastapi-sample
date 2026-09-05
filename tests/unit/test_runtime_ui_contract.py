"""Static contract checks for the runtime-aware topology card."""

from pathlib import Path

from nabla.api.ui import render_api_root_page

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "nabla" / "api" / "assets"


def test_local_runtime_topology_is_rendered_before_core_services() -> None:
    page = render_api_root_page(title_suffix="test", app_version="1.0.0")

    runtime = page.index('id="runtime-topology"')
    core = page.index('id="health-core-group-heading"')
    assert runtime < core
    assert "Local workstation runtime" in page
    assert "Runtime scope" in page
    assert "FastAPI Cloud runtime" not in page
    assert "FastAPI Cloud replicas" not in page
    assert "Vercel + FastAPI" not in page
    assert 'data-runtime-mode="local"' in page
    assert "Active egress IPs" in page
    assert "Recent egress IPs · 24 h" in page


def test_fastapi_cloud_runtime_keeps_production_context() -> None:
    page = render_api_root_page(
        title_suffix="test",
        app_version="1.0.0",
        is_fastapi_cloud=True,
    )

    assert "FastAPI Cloud production" in page
    assert "FastAPI Cloud runtime" in page
    assert "FastAPI Cloud replicas" in page
    assert 'data-runtime-mode="fastapi_cloud"' in page


def test_runtime_topology_uses_shared_health_board_request() -> None:
    javascript = (ASSETS / "api-runtime.js").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    styles = (ASSETS / "api.css").read_text(encoding="utf-8")

    assert 'from "./api-health-board.js"' in javascript
    assert "fetchHealthBoard()" in javascript
    assert 'from "./api-runtime.js"' in bootstrap
    assert "loadRuntimeTopology();" in bootstrap
    assert '@import url("./api-runtime.css")' in styles


def test_runtime_topology_does_not_claim_control_plane_replica_count() -> None:
    javascript = (ASSETS / "api-runtime.js").read_text(encoding="utf-8")

    assert "platform_replica_count" in javascript
    assert "runtime_mode" in javascript
    assert "control-plane only" in javascript
    assert "local process" in javascript
    assert "observed_instance_count" in javascript
    assert "active_egress_ips" in javascript
    assert "recent_egress_ips" in javascript
