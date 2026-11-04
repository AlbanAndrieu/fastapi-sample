"""Migration contracts: root is not the synthetic-sensor or notes page."""

from pathlib import Path

from fastapi.testclient import TestClient

from nabla.app_factory import create_minimal_app


ROOT = Path(__file__).resolve().parents[2]


def test_minimal_application_root_is_db_independent() -> None:
    app = create_minimal_app()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Operations Overview" in response.text
    assert "home-operations.js" in response.text
    assert "Sensor Dashboard" not in response.text
    assert "tempChart" not in response.text


def test_legacy_sensor_routes_are_not_the_root() -> None:
    source = (ROOT / "nabla/api/demo/sensor.py").read_text(encoding="utf-8")
    assert '@router.get("/demo/sensors"' in source
    assert '@router.get("/", response_class=HTMLResponse' not in source
    assert '"sensor_demo.html"' in source


def test_sensor_demo_and_heavy_charts_remain_off_the_main_page() -> None:
    root = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    demo = (ROOT / "templates/sensor_demo.html").read_text(encoding="utf-8")
    assert "home-operator-detail" in root
    assert 'href="/api"' in root
    assert "Pressure" not in root
    assert "Humidity" not in root
    assert "tempChart" in demo
    assert "humidityChart" in demo
    assert "pressureChart" in demo


def test_main_dashboard_uses_existing_endpoint_contracts_without_direct_promql() -> None:
    script = (ROOT / "nabla/api/assets/home-operations.js").read_text(encoding="utf-8")
    assert 'fetchJSON("/api/ui/services")' in script
    assert 'fetchJSON("/api/ui/session"' in script
    assert 'fetchJSON("/api/health-board"' in script
    assert 'fetchJSON("/api/topology-telemetry"' in script
    assert "prometheus.albandrieu.com" not in script
    assert "172.17." not in script
    assert "localStorage" not in script
    assert "Chart(" not in script
    assert "Math.random" not in script
