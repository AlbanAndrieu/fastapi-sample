"""Backward-compatible protection for administrative and diagnostic endpoints."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from starlette.testclient import TestClient

from nabla import access_control
from nabla.config_settings import APIDeploymentSettings


@pytest.fixture
def protected_app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Expose representative operational routes with configurable fake settings."""
    settings = SimpleNamespace(admin_access_key=None, diagnostics_access_key=None)
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)

    app = FastAPI()
    app.state.access_settings = settings
    app.middleware("http")(access_control.operations_access_middleware)

    @app.get("/admin")
    @app.get("/admin/users/list")
    @app.get("/health")
    @app.get("/healthz")
    @app.get("/api/homelab-topology")
    @app.get("/api/homelab/health")
    def success() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_operational_routes_remain_open_without_access_keys(
    protected_app: TestClient,
) -> None:
    assert protected_app.get("/admin").status_code == 200
    assert protected_app.get("/healthz").status_code == 200
    assert protected_app.get("/api/homelab-topology").status_code == 200


def test_operational_access_keys_are_declared_as_application_settings() -> None:
    assert "admin_access_key" in APIDeploymentSettings.model_fields
    assert "diagnostics_access_key" in APIDeploymentSettings.model_fields


def test_admin_key_only_protects_administration(
    protected_app: TestClient,
) -> None:
    protected_app.app.state.access_settings.admin_access_key = SecretStr("admin-key")

    assert protected_app.get("/admin/users/list").status_code == 401
    assert protected_app.get("/healthz").status_code == 200
    assert (
        protected_app.get(
            "/admin/users/list",
            headers={"X-Admin-Key": "admin-key"},
        ).status_code
        == 200
    )


def test_diagnostics_key_accepts_bearer_and_keeps_liveness_public(
    protected_app: TestClient,
) -> None:
    settings = protected_app.app.state.access_settings
    settings.diagnostics_access_key = SecretStr("diagnostics-key")

    assert protected_app.get("/api/homelab/health").status_code == 401
    assert protected_app.get("/api/homelab-topology").status_code == 401
    assert protected_app.get("/health").status_code == 200
    assert (
        protected_app.get(
            "/healthz",
            headers={"Authorization": "Bearer diagnostics-key"},
        ).status_code
        == 200
    )
