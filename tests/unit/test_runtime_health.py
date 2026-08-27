"""Contract tests for the lightweight `/health` runtime view."""

from fastapi.testclient import TestClient

from server_app import app


def test_health_exposes_runtime_components_without_homelab_services() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["version"] == app.version
    assert set(payload["components"]) == {
        "api",
        "sensor",
        "streaming",
        "health_api",
    }
    assert payload["components"]["api"]["status"] == "healthy"
    assert payload["components"]["health_api"]["deep_health"] == "/healthz"
    assert payload["components"]["health_api"]["homelab_health"] == "/api/homelab/health"
    assert "services" not in payload
    assert "internal_services" not in payload
