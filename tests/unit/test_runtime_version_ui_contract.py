from pathlib import Path


def test_runtime_version_warning_is_dynamic_and_non_blocking() -> None:
    ui = Path("nabla/api/ui.py").read_text()
    javascript = Path("nabla/api/assets/api-runtime-version.js").read_text()
    health = Path("nabla/api/assets/api-health.js").read_text()
    routes = Path("nabla/api/health_routes.py").read_text()

    assert 'id="runtime-version-warning"' in ui
    assert "/api/runtime/version-status" in javascript
    assert "behind === true" in javascript
    assert "Update the TrueNAS service" in javascript
    assert "startRuntimeVersionMonitor" in health
    assert '"/api/runtime/version-status"' in routes


def test_truenas_flow_shows_target_pfsense_services_and_cloudflare_last() -> None:
    javascript = Path("nabla/api/assets/api-truenas.js").read_text()
    assert 'label: "TrueNAS target URL"' in javascript
    assert 'label: "pfSense LAN control + DNS"' in javascript
    assert 'label: "Cloudflare Tunnel"' in javascript
    assert "renderPfsenseServices" in javascript
    assert "output.push(cloudflareTunnelStage(data));" in javascript
    assert "no Cloudflare DNS or pfSense WAN hop" in javascript
