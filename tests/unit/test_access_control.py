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
    settings = SimpleNamespace(
        admin_access_key=None,
        diagnostics_access_key=None,
        mcp_ops_key=None,
        ops_route_policy_strict=False,
        homelab_trusted_cidrs="",
        homelab_trusted_proxy_cidrs="",
    )
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)

    app = FastAPI()
    app.state.access_settings = settings
    app.middleware("http")(access_control.operations_access_middleware)

    @app.get("/admin")
    @app.get("/admin/users/list")
    @app.get("/health")
    @app.get("/healthz")
    @app.get("/api/topology")
    @app.get("/api/topology-telemetry")
    @app.get("/api/homelab/future-secret")
    @app.get("/api/public-topology")
    @app.get("/api/homelab/declared-services")
    @app.get("/api/site/catalog/v2")
    @app.get("/api/ui/session")
    @app.get("/api/homelab-topology")
    @app.get("/api/homelab/runtime")
    @app.get("/api/homelab/status")
    @app.get("/api/runtime/topology")
    @app.get("/api/homelab/health")
    @app.get("/api/homelab/probes")
    @app.post("/api/health-board/cache/reset")
    def success() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_operational_routes_fail_closed_without_access_keys(
    protected_app: TestClient,
) -> None:
    assert protected_app.get("/admin").status_code == 503
    assert protected_app.get("/healthz").status_code == 503
    assert protected_app.get("/api/homelab-topology").status_code == 503
    assert protected_app.get("/api/runtime/topology").status_code == 503
    assert protected_app.post("/api/health-board/cache/reset").status_code == 503


def test_operational_access_keys_are_declared_as_application_settings() -> None:
    assert "admin_access_key" in APIDeploymentSettings.model_fields
    assert "diagnostics_access_key" in APIDeploymentSettings.model_fields


def test_admin_key_only_protects_administration(
    protected_app: TestClient,
) -> None:
    protected_app.app.state.access_settings.admin_access_key = SecretStr("admin-key")

    assert protected_app.get("/admin/users/list").status_code == 401
    assert protected_app.get("/healthz").status_code == 503
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
    assert protected_app.get("/api/homelab/probes").status_code == 401
    assert protected_app.get("/api/homelab/declared-services").status_code == 401
    assert protected_app.get("/api/homelab-topology").status_code == 401
    assert protected_app.get("/api/homelab/runtime").status_code == 401
    assert protected_app.get("/api/runtime/topology").status_code == 401
    assert protected_app.get("/api/homelab/status").status_code == 401
    assert protected_app.post("/api/health-board/cache/reset").status_code == 401
    assert protected_app.get("/api/public-topology").status_code == 401
    assert protected_app.get("/health").status_code == 200
    assert (
        protected_app.get(
            "/healthz",
            headers={"Authorization": "Bearer diagnostics-key"},
        ).status_code
        == 200
    )
    assert (
        protected_app.post(
            "/api/health-board/cache/reset",
            headers={"X-Diagnostics-Key": "diagnostics-key"},
        ).status_code
        == 200
    )


def test_known_sensitive_routes_fail_without_any_key(protected_app: TestClient) -> None:
    for path in (
        "/api/homelab-services",
        "/api/health-board",
        "/api/health-board/refresh-event",
        "/api/public-topology",
        "/metrics",
        "/mcp",
        "/private/ops/api/v1/services",
    ):
        response = protected_app.get(path)
        assert response.status_code == 503, path
        assert response.headers["cache-control"] == "private, no-store"
    assert protected_app.get("/health").status_code == 200


def test_strict_mode_denies_unclassified_routes(protected_app: TestClient) -> None:
    settings = protected_app.app.state.access_settings
    assert protected_app.get("/docs").status_code == 200
    settings.ops_route_policy_strict = True
    assert protected_app.get("/docs").status_code == 403
    assert protected_app.get("/api/unknown").status_code == 403
    assert protected_app.get("/health").status_code == 200
    assert protected_app.get("/api/public-topology").status_code == 503


def test_legacy_credentials_not_accepted_for_owner_jwt_route(
    protected_app: TestClient,
) -> None:
    settings = protected_app.app.state.access_settings
    settings.diagnostics_access_key = SecretStr("diagnostics-key")
    response = protected_app.get(
        "/private/ops/api/v1/services",
        headers={"X-Diagnostics-Key": "diagnostics-key"},
    )
    assert response.status_code == 503


def test_owner_cidr_requires_diagnostics_key_and_allowed_client(
    protected_app: TestClient,
) -> None:
    settings = protected_app.app.state.access_settings
    settings.homelab_trusted_cidrs = "82.66.4.247/32"
    settings.diagnostics_access_key = SecretStr("diagnostics-key")
    # TestClient's 'testclient' peer is intentionally not the home IP.
    assert (
        protected_app.get(
            "/api/homelab/health",
            headers={"X-Diagnostics-Key": "diagnostics-key"},
        ).status_code
        == 403
    )
    assert (
        protected_app.get(
            "/api/homelab/health",
            headers={"X-Diagnostics-Key": "wrong"},
        ).status_code
        == 401
    )
    assert protected_app.get("/health").status_code == 200
    # A forged XFF / CF-Connecting-IP header must not bypass the allowlist.
    assert (
        protected_app.get(
            "/api/homelab/health",
            headers={
                "X-Diagnostics-Key": "diagnostics-key",
                "X-Forwarded-For": "82.66.4.247",
                "CF-Connecting-IP": "82.66.4.247",
            },
        ).status_code
        == 403
    )


def test_cidr_disabled_does_not_break_existing_diagnostics_key(
    protected_app: TestClient,
) -> None:
    settings = protected_app.app.state.access_settings
    settings.homelab_trusted_cidrs = ""
    settings.diagnostics_access_key = SecretStr("diagnostics-key")
    assert (
        protected_app.get(
            "/api/homelab/health",
            headers={"X-Diagnostics-Key": "diagnostics-key"},
        ).status_code
        == 200
    )


def test_site_catalog_service_key_never_weakens_owner_cidr(protected_app: TestClient) -> None:
    """Vercel may request a non-sensitive view, never the owner inventory."""
    settings = protected_app.app.state.access_settings
    settings.homelab_trusted_cidrs = "82.66.4.247/32"
    assert protected_app.get("/api/site/catalog/v2").status_code == 503
    settings.diagnostics_access_key = SecretStr("diagnostics-key")
    response = protected_app.get("/api/site/catalog/v2")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert protected_app.get("/api/site/catalog/v2", headers={"X-Diagnostics-Key": "wrong"}).status_code == 401
    valid_headers = {"X-Diagnostics-Key": "diagnostics-key"}
    assert protected_app.get("/api/site/catalog/v2", headers=valid_headers).status_code == 200
    assert protected_app.get("/api/homelab-services", headers=valid_headers).status_code == 403


def test_temporary_readonly_diagnostics_restores_probes_without_write_access(
    protected_app: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Temporary public GET mode cannot unlock state changes or admin routes."""
    monkeypatch.setenv("HOMELAB_PUBLIC_DIAGNOSTICS_READONLY", "true")
    for path in (
        "/healthz", "/api/topology", "/api/topology-telemetry",
        "/api/homelab-topology", "/api/runtime/topology",
        "/api/homelab/health", "/api/homelab/probes",
        "/api/site/catalog/v2",
    ):
        response = protected_app.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.headers["cache-control"] == "private, no-store"
    assert protected_app.post("/api/health-board/cache/reset").status_code == 503
    assert protected_app.get("/admin").status_code == 503
    assert protected_app.get("/metrics").status_code == 503
    # A future addition under /api/homelab must not be public by accident.
    assert protected_app.get("/api/homelab/future-secret").status_code == 404

    monkeypatch.setenv("HOMELAB_PUBLIC_DIAGNOSTICS_READONLY", "false")
    assert protected_app.get("/api/homelab/probes").status_code == 503
