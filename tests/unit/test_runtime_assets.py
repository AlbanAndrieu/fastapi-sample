"""Regression tests for the runtime-topology UI assets and route."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.routes import register_routes


def test_runtime_topology_assets_are_served() -> None:
    app = FastAPI(version="test-version")
    register_routes(app)
    client = TestClient(app)

    javascript = client.get("/api/assets/api-runtime.js")
    styles = client.get("/api/assets/api-runtime.css")

    assert javascript.status_code == 200
    assert "javascript" in javascript.headers["content-type"]
    assert styles.status_code == 200
    assert "text/css" in styles.headers["content-type"]
    assert "observed_instance_count" in javascript.text
    assert ".runtime-topology" in styles.text


def test_runtime_topology_route_is_registered() -> None:
    app = FastAPI(version="test-version")
    register_routes(app)

    paths = {route.path for route in app.routes}

    assert "/api/runtime/topology" in paths
