"""Route-contract tests for the extracted health router."""

from unittest.mock import AsyncMock

from fastapi import FastAPI

from nabla.api import catalog_routes
from nabla.api import site_architecture_catalog as v2
from nabla.api.health_routes import register_health_routes


def test_health_routes_keep_public_paths_once() -> None:
    app = FastAPI()

    register_health_routes(app)

    paths = [getattr(route, "path", None) for route in app.routes]
    expected = {
        "/api/homelab-services",
        "/api/public-topology",
        "/api/homelab-topology",
        "/api/homelab/health",
        "/api/homelab/probes",
        "/api/health-board",
        "/api/health-board/cache/reset",
        "/livez",
        "/readyz",
        "/healthz",
        "/sickz",
        "/sentry-debug",
    }

    for path in expected:
        assert paths.count(path) == 1


def test_health_routes_keep_openapi_tags() -> None:
    app = FastAPI()

    register_health_routes(app)

    tagged = {
        route.path: set(route.tags or [])
        for route in app.routes
        if getattr(route, "path", None)
        in {
            "/api/homelab-services",
            "/api/homelab-topology",
            "/api/homelab/health",
            "/api/homelab/probes",
            "/api/health-board",
            "/livez",
            "/readyz",
            "/healthz",
            "/sickz",
        }
    }

    assert tagged["/api/homelab-services"] == {"Homelab"}
    assert tagged["/api/homelab-topology"] == {"Homelab"}
    assert tagged["/api/homelab/health"] == {"Homelab", "Health"}
    assert tagged["/api/homelab/probes"] == {"Homelab", "Health", "TrueNAS"}
    assert tagged["/api/health-board"] == {"Health"}
    assert tagged["/livez"] == {"Health"}
    assert tagged["/readyz"] == {"Health"}
    assert tagged["/healthz"] == {"Health"}
    assert tagged["/sickz"] == {"Health"}


def test_health_routes_have_unique_operation_ids() -> None:
    app = FastAPI()
    register_health_routes(app)

    operation_ids = [route.operation_id for route in app.routes if getattr(route, "operation_id", None) is not None]
    assert len(operation_ids) == len(set(operation_ids))


def test_homelab_routes_publish_response_models_in_openapi() -> None:
    app = FastAPI()

    register_health_routes(app)

    schema = app.openapi()
    catalog = schema["paths"]["/api/homelab-services"]["get"]
    topology = schema["paths"]["/api/homelab-topology"]["get"]

    assert "$ref" not in catalog["responses"]["200"]["content"]["application/json"]["schema"]
    assert topology["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HomelabTopology"}


def test_application_openapi_includes_homelab_routes(test_app) -> None:
    response = test_app.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/homelab-services" in paths
    assert "/api/homelab-topology" in paths
    assert "/api/homelab/health" in paths
    assert "/api/homelab/probes" in paths


def test_application_serves_v2_routes_from_the_packaged_snapshot(test_app, monkeypatch) -> None:
    catalog_routes.clear_catalog_routes_cache()
    v2.reset_site_catalog_v2_cache()
    monkeypatch.setattr(v2, "_download_catalog_v2", AsyncMock(side_effect=ValueError("offline")))
    try:
        response = test_app.get("/api/homelab-services")
    finally:
        catalog_routes.clear_catalog_routes_cache()

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 2
    truenas = next(row for row in payload["services"] if row["id"] == "truenas")
    assert truenas["entityRef"] == "resource:default/truenas"
    assert (truenas["external"], truenas["tunnelSecure"]) == (True, False)
