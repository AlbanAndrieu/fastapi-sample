"""Tests for version resolution and the public endpoint."""

from fastapi.testclient import TestClient

from nabla.main import app
from nabla.version import resolve_release_version


def test_release_version_environment_override(monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "v2.4.6")

    assert resolve_release_version() == "2.4.6"


def test_invalid_release_version_uses_generated_fallback(monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "unknown")

    assert resolve_release_version() == "1.3.7"


def test_version_endpoint_exposes_api_and_release_versions():
    response = TestClient(app).get("/v2/version")

    assert response.status_code == 200
    assert response.json() == {
        "version": "v0+1.3.7",
        "api_version": "v0",
        "release_version": "1.3.7",
    }
