"""Tests for version resolution and the public endpoint."""

from fastapi.testclient import TestClient

from nabla.main import app
from nabla.version import resolve_release_version


def test_release_version_environment_override(monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "v2.4.6")

    assert resolve_release_version() == "2.4.6"


def test_invalid_release_version_uses_generated_fallback(monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "unknown")

    assert resolve_release_version() == "1.4.0"


def test_version_endpoint_exposes_api_release_and_mcp_metadata():
    response = TestClient(app).get("/v2/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v0+1.4.0"
    assert payload["api_version"] == "v0"
    assert payload["release_version"] == "1.4.0"
    assert payload["service"] == "fastapi-sample"
    assert payload["mcp"]["transport"] == "streamable-http"
    assert payload["mcp"]["endpoint"] == "/mcp"
    assert payload["mcp"]["openapi_endpoint"] == "/openapi.json"
    assert payload["mcp"]["api_ui"] == "/api"
    assert payload["knowledge"]["alban_profile"] == "https://www.albanandrieu.com/"
