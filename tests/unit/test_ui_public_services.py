"""Temporary public overview must never leak owner-only diagnostic evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla import access_control
from nabla.api import health_routes, ui_public_services
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
    board = {
        "state": "fresh",
        "homelab": {
            "services": [
                {
                    "id": "garage",
                    "effective_state": "warn",
                    "internalHost": "172.17.0.24",
                    "url": "https://private.invalid:8443",
                    "secret": "NEVER-ECHO",
                },
            ],
        },
    }
    payload = project_public_ui_services(_catalog(), board).model_dump()
    assert payload["model"] == "public-service-overview"
    assert payload["services"] == [
        {"name": "Garage", "kind": "Component", "state": "warn"},
        {"name": "postgres", "kind": "Resource", "state": "unknown"},
    ]
    assert payload["catalogSource"] == "backstage-v2"
    assert set(payload) == {
        "catalogSource",
        "schemaVersion",
        "model",
        "catalogRevision",
        "boardState",
        "services",
    }
    assert not any(sensitive in str(payload) for sensitive in ("172.17.0.24", "private.invalid", "8443", "NEVER-ECHO", "entityRef"))


def test_unverified_states_stay_unknown():
    board = {
        "state": "stale",
        "homelab": {
            "services": [{"id": "garage", "effective_state": "fail"}],
        },
    }
    assert project_public_ui_services(_catalog(), board).services[0].state == "unknown"


def test_temporary_switch_disables_only_public_projection(monkeypatch):
    monkeypatch.delenv("HOMELAB_UI_PUBLIC_READONLY_ENABLED", raising=False)
    monkeypatch.setenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", "false")
    # Old environment config must not silently suppress the temporary fix.
    assert public_ui_services_enabled()
    monkeypatch.setenv("HOMELAB_UI_PUBLIC_READONLY_ENABLED", "false")
    assert not public_ui_services_enabled()


def test_anonymous_public_overview_never_opens_raw_diagnostics(monkeypatch):
    monkeypatch.setenv("HOMELAB_UI_PUBLIC_READONLY_ENABLED", "true")

    async def fake_overview(_request):
        return project_public_ui_services(_catalog(), {"state": "pending"})

    monkeypatch.setattr(
        health_routes,
        "get_public_ui_services",
        AsyncMock(side_effect=fake_overview),
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

    monkeypatch.setenv("HOMELAB_UI_PUBLIC_READONLY_ENABLED", "false")
    assert client.get("/api/ui/services").status_code == 404
    assert client.get("/api/health-board").status_code != 200


async def _broken_health_board(_request):
    raise RuntimeError("Private upstream unavailable at 172.17.0.24:9999")


@pytest.mark.asyncio
async def test_directory_survives_failed_diagnostics_with_unknown(monkeypatch):
    monkeypatch.setattr(
        ui_public_services,
        "fetch_site_catalog_v2",
        AsyncMock(return_value=_catalog()),
    )
    monkeypatch.setattr(
        "nabla.api.health_board.get_health_board_snapshot",
        _broken_health_board,
    )

    result = await ui_public_services.get_public_ui_services(None)
    assert result.boardState == "pending"
    assert all(row.state == "unknown" for row in result.services)
    assert "172.17.0.24" not in str(result.model_dump())


@pytest.mark.asyncio
async def test_public_directory_survives_backstage_outage_with_real_snapshot_states(monkeypatch):
    from nabla.api.site_architecture_catalog import SiteCatalogV2Unavailable

    services = [
        SimpleNamespace(name="Garage", service_id="garage"),
        SimpleNamespace(name="Gatus", service_id="gatus"),
        SimpleNamespace(name="Vaultwarden", service_id="vaultwarden"),
        SimpleNamespace(name="172.17.0.24:1234", service_id="internal-ip"),
        SimpleNamespace(name="Secret https://private.example/", service_id="secret"),
    ]
    remote = AsyncMock(side_effect=SiteCatalogV2Unavailable("Backstage offline"))
    monkeypatch.setattr(ui_public_services, "fetch_site_catalog_v2", remote)
    monkeypatch.setattr(
        ui_public_services, "packaged_homelab_catalog",
        lambda: SimpleNamespace(services=services),
    )
    monkeypatch.setattr(ui_public_services, "_backstage_retry_after", 0.0)
    monkeypatch.setattr(
        "nabla.api.health_board.get_health_board_snapshot",
        AsyncMock(return_value={
            "state": "fresh",
            "homelab": {"services": [
                {"id": "garage", "effective_state": "warn", "secret": "NEVER-ECHO"},
                {"id": "gatus", "effective_state": "ok", "internalHost": "172.17.0.24"},
                {"id": "vaultwarden", "effective_state": "fail", "probe_stale": True},
            ]},
        }),
    )
    result = await ui_public_services.get_public_ui_services(None)
    assert result.catalogSource == "bootstrap-snapshot"
    assert result.boardState == "fresh"
    assert {item.name: item.state for item in result.services} == {
        "Garage": "warn", "Gatus": "ok", "Vaultwarden": "unknown",
    }
    assert not any(v in result.model_dump_json() for v in ("172.17.0.24", "private.example", "NEVER-ECHO"))
    assert result.catalogRevision.startswith("sha256:")

    # No repeated failing Backstage fetch on the anonymous refresh loop.
    again = await ui_public_services.get_public_ui_services(None)
    assert again.model_dump() == result.model_dump()
    assert remote.await_count == 1


@pytest.mark.asyncio
async def test_bootstrap_never_fabricates_state_from_stale_or_ambiguous_evidence(monkeypatch):
    from nabla.api.site_architecture_catalog import SiteCatalogV2Unavailable

    monkeypatch.setattr(
        ui_public_services, "fetch_site_catalog_v2",
        AsyncMock(side_effect=SiteCatalogV2Unavailable("offline")),
    )
    monkeypatch.setattr(
        ui_public_services, "packaged_homelab_catalog",
        lambda: SimpleNamespace(services=[
            SimpleNamespace(name="Garage", service_id="garage"),
            SimpleNamespace(name="Garage", service_id="garage-other"),
        ]),
    )
    monkeypatch.setattr(ui_public_services, "_backstage_retry_after", 0.0)
    monkeypatch.setattr(
        "nabla.api.health_board.get_health_board_snapshot",
        AsyncMock(return_value={
            "state": "fresh", "homelab": {"services": [
                {"id": "garage", "state": "ok"},
                {"id": "garage", "state": "fail"},
            ]},
        }),
    )
    ambiguous = await ui_public_services.get_public_ui_services(None)
    assert len(ambiguous.services) == 1
    assert ambiguous.services[0].state == "unknown"
    assert ambiguous.catalogSource == "bootstrap-snapshot"
