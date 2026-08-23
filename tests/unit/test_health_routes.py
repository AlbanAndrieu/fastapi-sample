"""Route-contract tests for the extracted health router."""

from fastapi import FastAPI

from nabla.api.health_routes import register_health_routes


def test_health_routes_keep_public_paths_once() -> None:
    app = FastAPI()

    register_health_routes(app)

    paths = [getattr(route, "path", None) for route in app.routes]
    expected = {
        "/api/homelab-services",
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
        in {"/api/homelab-services", "/api/homelab/health", "/healthz", "/sickz"}
    }

    assert tagged["/api/homelab-services"] == {"Homelab"}
    assert tagged["/api/homelab/health"] == {"Homelab", "Health"}
    assert tagged["/healthz"] == {"Health"}
    assert tagged["/sickz"] == {"Health"}
