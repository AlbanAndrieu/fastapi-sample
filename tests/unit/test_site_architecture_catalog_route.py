"""End-to-end API access policy for the no-fallback site catalog projection."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from pydantic import SecretStr
from starlette.testclient import TestClient

from nabla import access_control
from nabla.api import homelab_catalog
from nabla.api.health_routes import register_health_routes
from nabla.api.homelab_models import HomelabCatalog


def test_site_catalog_requires_key_but_does_not_bypass_owner_cidr(monkeypatch) -> None:
    settings = SimpleNamespace(
        diagnostics_access_key=SecretStr("site-diagnostics-key"),
        admin_access_key=None,
        mcp_ops_key=None,
        ops_route_policy_strict=False,
        homelab_trusted_cidrs="82.66.4.247/32",
        homelab_trusted_proxy_cidrs="",
    )
    monkeypatch.setattr(access_control, "get_settings", lambda: settings)
    catalog = HomelabCatalog.model_validate(
        {
            "services": [
                {
                    "id": "garage",
                    "name": "Garage",
                    "internalHost": "172.17.0.24",
                    "internalPort": 3900,
                    "external": False,
                },
            ],
        },
    )
    source = AsyncMock(return_value=catalog)
    monkeypatch.setattr(homelab_catalog, "fetch_authoritative_homelab_catalog", source)
    app = FastAPI()
    app.middleware("http")(access_control.operations_access_middleware)
    register_health_routes(app)
    client = TestClient(app)

    assert client.get("/api/site/catalog/v1").status_code == 401
    assert client.get("/api/site/catalog/v1", headers={"X-Diagnostics-Key": "wrong"}).status_code == 401
    assert source.await_count == 0
    correct = {"X-Diagnostics-Key": "site-diagnostics-key"}
    response = client.get("/api/site/catalog/v1", headers=correct)
    assert response.status_code == 200
    assert response.json() == {"version": 1, "services": [{"id": "garage", "name": "Garage"}]}
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert client.get("/api/homelab-services", headers=correct).status_code == 403

    source.side_effect = homelab_catalog.AuthoritativeCatalogUnavailable("unavailable")
    failing = client.get("/api/site/catalog/v1", headers=correct)
    assert failing.status_code == 503
    assert "no-store" in failing.headers["cache-control"]
    assert "172.17.0.24" not in failing.text
    assert "site-diagnostics-key" not in failing.text
