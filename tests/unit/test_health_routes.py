"""FastAPI route contracts after the Site Backstage v2 catalog cutover."""

from fastapi import FastAPI

from nabla.api.health_routes import register_health_routes


def _paths(app: FastAPI) -> list[str]:
    return [route.path for route in app.routes if hasattr(route, "path")]


def test_health_routes_register_v2_without_legacy_catalog() -> None:
    app = FastAPI()
    register_health_routes(app)
    paths = _paths(app)
    expected = {
        "/api/site/catalog/v2",
        "/api/site/health/v2",
        "/api/ui/services",
        "/api/public-topology",
        "/api/homelab-topology",  # Private topology UI still consumes this view.
        "/api/homelab/declared-services",
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
        assert paths.count(path) == 1, path
    assert "/api/homelab-services" not in paths
    assert "/api/public-homelab/v1" not in paths


def test_health_routes_keep_openapi_tags() -> None:
    app = FastAPI()
    register_health_routes(app)
    tagged = {
        route.path: set(route.tags or [])
        for route in app.routes
        if getattr(route, "path", None)
        in {
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
    assert tagged["/api/homelab-topology"] == {"Homelab"}
    assert tagged["/api/homelab/health"] == {"Homelab", "Health"}
    assert tagged["/api/homelab/probes"] == {"Homelab", "Health", "TrueNAS"}
    assert tagged["/api/health-board"] == {"Health"}
    for path in ("/livez", "/readyz", "/healthz", "/sickz"):
        assert tagged[path] == {"Health"}


def test_health_routes_have_unique_operation_ids() -> None:
    app = FastAPI()
    register_health_routes(app)
    operation_ids = [route.operation_id for route in app.routes if getattr(route, "operation_id", None) is not None]
    assert len(operation_ids) == len(set(operation_ids))


def test_private_topology_remains_typed_and_legacy_http_absent() -> None:
    app = FastAPI()
    register_health_routes(app)
    schema = app.openapi()
    topology_schema = schema["paths"]["/api/homelab-topology"]["get"]
    body_schema = topology_schema["responses"]["200"]["content"]["application/json"]["schema"]
    assert body_schema == {"$ref": "#/components/schemas/HomelabTopology"}
    assert "/api/homelab-services" not in schema["paths"]
    assert "/api/public-homelab/v1" not in schema["paths"]


def test_application_openapi_excludes_retired_catalog_routes(test_app) -> None:
    response = test_app.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/homelab-services" not in paths
    assert "/api/public-homelab/v1" not in paths
    assert "/api/homelab-topology" in paths
    assert "/api/homelab/health" in paths
    assert "/api/homelab/probes" in paths


def test_flag_cannot_reregister_retired_routes(test_app, monkeypatch) -> None:
    monkeypatch.setenv("HOMELAB_V1_HTTP_ENABLED", "true")
    assert "/api/homelab-services" not in _paths(test_app.app)
    assert "/api/public-homelab/v1" not in _paths(test_app.app)
