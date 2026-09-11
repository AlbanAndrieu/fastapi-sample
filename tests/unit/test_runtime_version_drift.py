"""Regression coverage for homelab-to-cloud runtime version drift UI."""

import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.routes import register_routes

ASSETS = Path(__file__).resolve().parents[2] / "nabla" / "api" / "assets"


def test_runtime_version_endpoint_is_public_sanitized_and_cross_origin() -> None:
    app = FastAPI(version="1.13.14")
    register_routes(app)
    response = TestClient(app).get("/api/runtime-version")

    assert response.status_code == 200
    assert response.json()["version"] == "1.13.14"
    assert set(response.json()) == {"version", "runtime_mode"}
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_homelab_version_warning_compares_against_fastapi_cloud() -> None:
    script = (ASSETS / "api-version-drift.js").read_text(encoding="utf-8")
    bootstrap = (ASSETS / "api-health.js").read_text(encoding="utf-8")
    cloud_url = re.search(
        r'const FASTAPI_CLOUD_VERSION_URL\s*=\s*"([^"]+)";',
        script,
    )

    assert cloud_url is not None
    assert cloud_url.group(1) == "https://fastapi-sample.fastapicloud.dev/api/runtime-version"
    assert 'runtime?.dataset?.runtimeMode !== "homelab"' in script
    assert 'warning.textContent = "⚠️";' in script
    assert "compareVersions(localVersion, cloudVersion) !== -1" in script
    assert "is behind FastAPI Cloud" in script
    assert "Update the TrueNAS service." in script
    assert "warning.title = message;" in script
    assert "installRuntimeVersionDriftWarning();" in bootstrap


def test_semver_comparison_contract_is_patch_aware() -> None:
    script = (ASSETS / "api-version-drift.js").read_text(encoding="utf-8")

    assert r"/(\d+)\.(\d+)\.(\d+)/" in script
    assert "a[index] < b[index] ? -1 : 1" in script
