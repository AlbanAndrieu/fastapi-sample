"""Application factory contracts: minimal app isolation and default app parity."""

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

import nabla.lifespan as lifecycle
from nabla.app_factory import create_app, create_minimal_app
from nabla.app_features import AppFeatures
from nabla.main import app as production_app
from nabla.main import mcp, mcp_app

DATABASE_PATHS = {"/auth/jwt/login", "/notes/", "/users/me", "/"}
MCP_PATHS = {"/v1/mcp/ops/servers"}
RAG_PATHS = {"/run"}


def _forbid(name: str):
    def _fail(*_args, **_kwargs):
        raise AssertionError(f"minimal app must not call {name}")

    return _fail


@pytest.fixture
def isolated_lifecycle(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fail loudly on any PostgreSQL, Redis, MCP client or socket I/O."""
    database = SimpleNamespace(
        connect=AsyncMock(side_effect=AssertionError("PostgreSQL connect")),
        disconnect=AsyncMock(),
    )
    db_pool = SimpleNamespace(close=Mock())
    redis = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(lifecycle, "database", database)
    monkeypatch.setattr(lifecycle, "db_pool", db_pool)
    monkeypatch.setattr(lifecycle, "redis", redis)
    monkeypatch.setattr(lifecycle, "init_db", AsyncMock(side_effect=AssertionError("schema DDL")))
    monkeypatch.setattr(lifecycle, "initialize_mcp_clients", AsyncMock(side_effect=AssertionError("MCP clients")))
    monkeypatch.setattr(lifecycle, "start_event_listener", _forbid("start_event_listener"))
    monkeypatch.setattr(lifecycle, "runtime_topology_heartbeat", _forbid("runtime_topology_heartbeat"))
    monkeypatch.setattr(socket.socket, "connect", _forbid("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", _forbid("socket.create_connection"))
    return SimpleNamespace(database=database, db_pool=db_pool, redis=redis)


def _openapi_paths(app) -> set[str]:
    return set(app.openapi()["paths"])


def test_minimal_features_disable_every_subsystem() -> None:
    assert AppFeatures.minimal() == AppFeatures(
        database=False,
        redis=False,
        observability=False,
        mcp=False,
        rag=False,
    )
    assert AppFeatures() == AppFeatures(
        database=True,
        redis=True,
        observability=True,
        mcp=True,
        rag=True,
    )


def test_minimal_app_serves_liveness_without_external_services(isolated_lifecycle) -> None:
    app = create_minimal_app()

    with TestClient(app) as client:
        response = client.get("/livez")
        assert app.state.redis is None

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"] == "liveness"
    assert payload["status"] == "alive"
    assert payload["version"] == app.version
    isolated_lifecycle.database.connect.assert_not_awaited()
    isolated_lifecycle.database.disconnect.assert_not_awaited()
    isolated_lifecycle.db_pool.close.assert_not_called()
    isolated_lifecycle.redis.aclose.assert_not_awaited()
    lifecycle.initialize_mcp_clients.assert_not_awaited()


def test_minimal_app_omits_disabled_subsystem_routes() -> None:
    app = create_app(AppFeatures.minimal())
    paths = _openapi_paths(app)

    assert app.state.features == AppFeatures.minimal()
    assert app.state.mcp is None
    assert app.state.mcp_app is None
    assert {"/livez", "/readyz", "/healthz", "/api/homelab/status"} <= paths
    assert paths.isdisjoint(DATABASE_PATHS | MCP_PATHS | RAG_PATHS)
    assert not any(isinstance(route, Mount) and route.path == "" for route in app.routes)


def test_single_feature_switch_only_removes_its_routes() -> None:
    without_rag = _openapi_paths(create_app(AppFeatures(observability=False, mcp=False, rag=False)))
    with_rag = _openapi_paths(create_app(AppFeatures(observability=False, mcp=False)))

    assert with_rag - without_rag == RAG_PATHS


def test_default_factory_matches_exported_production_app() -> None:
    default_app = create_app()

    assert _openapi_paths(default_app) == _openapi_paths(production_app)
    assert DATABASE_PATHS | MCP_PATHS | RAG_PATHS <= _openapi_paths(production_app)
    assert production_app.state.features == AppFeatures()
    assert mcp is production_app.state.mcp
    assert mcp_app is production_app.state.mcp_app
    assert mcp is not None
    assert any(isinstance(route, Mount) and route.app is mcp_app for route in production_app.routes)
