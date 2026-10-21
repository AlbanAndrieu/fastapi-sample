"""Temporary public overview must never leak owner-only diagnostic evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla import access_control
from nabla.api import health_routes
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteV2Entity,
    SiteV2Metadata,
)
from nabla.api.ui_public_services import (
    project_public_ui_services,
    public_ui_services_enabled,
)


def _catalog():
    return SiteArchitectureCatalogV2(
        catalogRevision="sha256:" + "a" * 64,
        entities=[
            SiteV2Entity(
                kind="Component",
                entityRef="component:default/garage",
                sourcePath="apps/garage/catalog-info.yaml",
                metadata=SiteV2Metadata(name="garage", title="Garage"),
                spec={"type": "service"},
            ),
            SiteV2Entity(
                kind="Resource",
                entityRef="resource:default/postgres",
                sourcePath="apps/postgres/catalog-info.yaml",
                metadata=SiteV2Metadata(name="postgres"),
                spec={},
            ),
        ],
    )


def test_public_overview_strictly_excludes_probe_and_network_fields():
    board = {"state": "fresh", "homelab": {"services": [
        {"id": "garage", "effective_state": "warn", "internalHost": "172.17.0.24",
         "url": "https://private.invalid:8443", "secret": "NEVER-ECHO"}
    ]}}
    payload = project_public_ui_services(_catalog(), board).model_dump()
    assert payload["model"] == "public-service-overview"
    assert payload["services"] == [
        {"name": "Garage", "kind": "Component", "state": "warn"},
        {"name": "postgres", "kind": "Resource", "state": "unknown"},
    ]
    assert set(payload) == {"schemaVersion", "model", "catalogRevision", "boardState", "services"}
    assert not any(
        sensitive in str(payload)
        for sensitive in ("172.17.0.24", "private.invalid", "8443", "NEVER-ECHO", "entityRef")
    )


def test_unverified_states_stay_unknown():
    board = {"state": "stale", "homelab": {"services": [
        {"id": "garage", "effective_state": "fail"},
    ]}}
    assert project_public_ui_services(_catalog(), board).services[0].state == "unknown"


def test_temporary_switch_disables_only_public_projection(monkeypatch):
    monkeypatch.delenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", raising=False)
    assert public_ui_services_enabled()
    monkeypatch.setenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", "false")
    assert not public_ui_services_enabled()


def test_anonymous_public_overview_never_opens_raw_diagnostics(monkeypatch):
    monkeypatch.setenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", "true")
    async def fake_overview(_request):
        return project_public_ui_services(_catalog(), {"state": "pending"})

    monkeypatch.setattr(
        health_routes, "get_public_ui_services", AsyncMock(side_effect=fake_overview)
    )
    monkeypatch.setattr(
        access_control,
        "get_settings",
        lambda: SimpleNamespace(
            diagnostics_access_key=None,
            admin_access_key=None,
            mcp_ops_key=None,
            ops_route_policy_strict=True,
            homelab_trusted_cidrs="",
        ),
    )
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    health_routes._register_homelab_catalog_routes(app)

    @app.get("/api/health-board")
    async def private():
        return {"internalHost": "172.17.0.24"}

    client = TestClient(app)
    response = client.get("/api/ui/services")
    assert response.status_code == 200
    assert response.json()["services"][0]["state"] == "unknown"
    assert "internalHost" not in response.text
    assert client.get("/api/health-board").status_code != 200

    monkeypatch.setenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", "false")
    assert client.get("/api/ui/services").status_code == 404
    assert client.get("/api/health-board").status_code != 200
