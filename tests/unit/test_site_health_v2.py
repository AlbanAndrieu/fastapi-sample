"""Contract and privacy tests for the SITE health v2 service."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nabla import access_control
from nabla.api import health_routes
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteV2Entity,
    SiteV2Metadata,
)
from nabla.api.site_health_v2 import project_site_health_v2


def _catalog():
    return SiteArchitectureCatalogV2(
        catalogRevision="sha256:" + "a" * 64,
        entities=[
            SiteV2Entity(
                kind="Component",
                entityRef="component:default/garage",
                sourcePath="apps/garage/catalog-info.yaml",
                metadata=SiteV2Metadata(name="garage"),
                spec={},
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


def test_allowlist_revision_and_no_operational_disclosure():
    sample = {
        "state": "fresh",
        "homelab": {
            "services": [
                {
                    "id": "garage",
                    "effective_state": "warn",
                    "url": "https://private.invalid",
                    "internalHost": "172.17.0.24",
                    "token": "SECRET",
                },
            ],
        },
    }
    wire = project_site_health_v2(_catalog(), sample).model_dump()
    assert wire["schemaVersion"] == 2
    assert wire["model"] == "backstage-health"
    assert wire["catalogRevision"] == "sha256:" + "a" * 64
    assert wire["services"][0] == {
        "entityRef": "component:default/garage",
        "state": "warn",
    }
    assert wire["services"][1]["state"] == "unknown"
    assert not any(s in str(wire) for s in ("SECRET", "172.17.0.24", "https://"))


def test_fail_closed_unknown_on_stale_or_ambiguous_evidence():
    sample = {
        "state": "fresh",
        "homelab": {
            "services": [
                {"id": "garage", "state": "fail"},
                {"id": "garage", "state": "ok"},
            ],
        },
    }
    assert project_site_health_v2(_catalog(), sample).services[0].state == "unknown"
    sample["homelab"]["services"] = [{"id": "garage", "state": "fail"}]
    sample["state"] = "stale"
    assert project_site_health_v2(_catalog(), sample).services[0].state == "unknown"
    sample["state"] = "fresh"
    sample["homelab"]["services"][0]["observation_stale"] = True
    assert project_site_health_v2(_catalog(), sample).services[0].state == "unknown"


def test_only_machine_key_can_fetch_site_health(monkeypatch):
    settings = SimpleNamespace(
        diagnostics_access_key=SecretStr("site-machine-key"),
        admin_access_key=None,
        mcp_ops_key=None,
        ops_route_policy_strict=False,
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="",
    )
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)
    monkeypatch.setattr(
        health_routes,
        "fetch_site_health_v2",
        AsyncMock(return_value=project_site_health_v2(_catalog(), {"state": "pending"})),
    )
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    health_routes._register_homelab_catalog_routes(app)
    client = TestClient(app)
    assert client.get("/api/site/health/v2").status_code == 401
    assert (
        client.get("/api/site/health/v2", headers={"X-Diagnostics-Key": "bad"}).status_code
        == 401
    )
    response = client.get(
        "/api/site/health/v2", headers={"X-Diagnostics-Key": "site-machine-key"},
    )
    assert response.status_code == 200
    assert response.json()["boardState"] == "pending"
    assert response.headers["cache-control"] == "no-store, max-age=0"
