"""Route-contract tests for the extracted health router."""

from fastapi import FastAPI

from nabla.api.health_routes import register_health_routes


def test_health_routes_keep_public_paths_once() -> None:
    app = FastAPI()

    register_health_routes(app)

    paths = [getattr(route, "path", None) for route in app.routes]
    expected = {
        "/api/homelab-services",
        "/api/homelab-topology",
        "/api/homelab/health",
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
            "/healthz",
            "/sickz",
        }
    }

    assert tagged["/api/homelab-services"] == {"Homelab"}
    assert tagged["/api/homelab-topology"] == {"Homelab"}
    assert tagged["/api/homelab/health"] == {"Homelab", "Health"}
    assert tagged["/healthz"] == {"Health"}
    assert tagged["/sickz"] == {"Health"}


def test_homelab_routes_publish_response_models_in_openapi() -> None:
    app = FastAPI()

    register_health_routes(app)

    schema = app.openapi()
    catalog = schema["paths"]["/api/homelab-services"]["get"]
    topology = schema["paths"]["/api/homelab-topology"]["get"]

    assert catalog["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HomelabCatalog"}
    assert topology["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HomelabTopology"}


def test_application_openapi_includes_homelab_routes(test_app) -> None:
    response = test_app.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/homelab-services" in paths
    assert "/api/homelab-topology" in paths
    assert "/api/homelab/health" in paths


def test_application_serves_packaged_homelab_catalog(test_app) -> None:
    response = test_app.get("/api/homelab-services")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["services"]
