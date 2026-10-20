"""Auth boundary of the canonical Backstage v2 site endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from pydantic import SecretStr
from starlette.testclient import TestClient

from nabla import access_control
from nabla.api import site_architecture_catalog as v2
from nabla.api.health_routes import register_health_routes


def test_v2_site_reader_requires_key_and_preserves_owner_cidr(monkeypatch) -> None:
    settings = SimpleNamespace(
        diagnostics_access_key=SecretStr("site-diagnostics-key"),
        admin_access_key=None,
        mcp_ops_key=None,
        ops_route_policy_strict=False,
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="",
    )
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)
    entity = v2.SiteV2Entity(
        kind="Component",
        entityRef="component:default/api",
        sourcePath="apps/api/catalog-info.yaml",
        metadata=v2.SiteV2Metadata(name="api"),
        spec={"type": "service"},
    )
    catalog = v2.SiteArchitectureCatalogV2(
        catalogRevision="sha256:" + "a" * 64, entities=[entity],
    )
    source = AsyncMock(return_value=catalog)
    monkeypatch.setattr(v2, "fetch_site_catalog_v2", source)
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    register_health_routes(app)
    client = TestClient(app)

    assert client.get("/api/site/catalog/v1").status_code in (403, 404)
    assert client.get("/api/site/catalog/v2").status_code == 401
    assert client.get("/api/site/catalog/v2", headers={"X-Diagnostics-Key": "wrong"}).status_code == 401
    assert source.await_count == 0
    headers = {"X-Diagnostics-Key": "site-diagnostics-key"}
    response = client.get("/api/site/catalog/v2", headers=headers)
    assert response.status_code == 200
    assert response.json()["schemaVersion"] == 2
    assert response.json()["model"] == "backstage"
    assert response.json()["entities"][0]["entityRef"] == "component:default/api"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert client.get("/api/homelab-services", headers=headers).status_code == 403

    source.side_effect = v2.SiteCatalogV2Unavailable("unavailable")
    failing = client.get("/api/site/catalog/v2", headers=headers)
    assert failing.status_code == 503
    assert "no-store" in failing.headers["cache-control"]
    assert "site-diagnostics-key" not in failing.text
