"""Application factory contracts: minimal app isolation and default app parity."""

import functools
import importlib
import socket
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount, Route

from nabla.api import health_contracts, runtime_topology
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
    assert any(isinstance(route, Route) and route.path == "/mcp" and route.app is mcp_app for route in production_app.routes)
    assert not any(isinstance(route, Mount) and route.path == "" for route in production_app.routes)


SUBSYSTEMS = ("database", "redis", "observability", "mcp", "rag")
LEGACY_READINESS_KEYS = {"contract", "status", "version", "checked_at", "checks"}
LEGACY_REDIS_TOPOLOGY_KEYS = {
    "backend",
    "provider_attribution",
    "telemetry_scope",
    "key_count_scope",
    "configured",
    "available",
    "telemetry_available",
    "reason",
}
NO_EGRESS = {"ip": None, "observed": False, "cached": False, "source": "external_echo"}
redis_module = importlib.import_module("nabla.api.demo.socket.redis")


@pytest.fixture(autouse=True)
def _workstation_dependency_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the dependency policy: workstation runtime, no explicit *_REQUIRED."""
    monkeypatch.setattr(health_contracts, "runtime_mode", lambda: "local")
    for variable in ("POSTGRES_REQUIRED", "REDIS_REQUIRED", "SUPABASE_REQUIRED"):
        monkeypatch.delenv(variable, raising=False)


def _optional(check: dict[str, object]) -> dict[str, object]:
    return {**check, "required": False}


def _disabled_check(subsystem: str) -> dict[str, object]:
    return {
        "reachable": None,
        "skipped": True,
        "state": "disabled",
        "reason": f"{subsystem} subsystem disabled by application features",
    }


@pytest.fixture
def dependency_probes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace readiness probes; tests opt in to a result, otherwise any call fails."""
    probes = SimpleNamespace(
        postgres=Mock(side_effect=AssertionError("PostgreSQL readiness probe")),
        redis=AsyncMock(side_effect=AssertionError("Redis readiness probe")),
    )
    monkeypatch.setattr(health_contracts, "check_postgres_sql", probes.postgres)
    monkeypatch.setattr(health_contracts, "check_redis_ping", probes.redis)
    # The public egress observer is not a feature-gated subsystem; keep it offline.
    monkeypatch.setattr(runtime_topology, "observe_public_egress_ip", AsyncMock(return_value=dict(NO_EGRESS)))
    return probes


@pytest.fixture(autouse=True)
def _authenticated_clients(unit_ops_access: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """/readyz and /api/runtime/topology are private diagnostics routes."""
    monkeypatch.setattr(
        sys.modules[__name__],
        "TestClient",
        functools.partial(TestClient, headers=unit_ops_access),
    )


def _probes_return(probes: SimpleNamespace, *, postgres: dict[str, object], redis: dict[str, object]) -> None:
    probes.postgres.side_effect = None
    probes.postgres.return_value = dict(postgres)
    probes.redis.side_effect = None
    probes.redis.return_value = dict(redis)


def test_minimal_app_readiness_reports_every_subsystem_disabled(isolated_lifecycle, dependency_probes) -> None:
    app = create_minimal_app()

    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["subsystems"] == dict.fromkeys(SUBSYSTEMS, "disabled")
    assert payload["checks"] == {"postgres": _optional(_disabled_check("database")), "redis": _optional(_disabled_check("redis"))}
    dependency_probes.postgres.assert_not_called()
    dependency_probes.redis.assert_not_awaited()
    isolated_lifecycle.database.connect.assert_not_awaited()


def test_minimal_app_runtime_topology_reports_redis_disabled(isolated_lifecycle, dependency_probes) -> None:
    app = create_minimal_app()

    with TestClient(app) as client:
        response = client.get("/api/runtime/topology")

    assert response.status_code == 200
    payload = response.json()
    assert payload["subsystems"] == dict.fromkeys(SUBSYSTEMS, "disabled")
    assert payload["redis"]["state"] == "disabled"
    assert payload["redis"]["configured"] is False
    assert payload["redis"]["available"] is False
    assert payload["aggregation"] == "local_only"
    assert payload["degraded"] is False
    isolated_lifecycle.redis.aclose.assert_not_awaited()


@pytest.mark.parametrize(
    ("disabled", "check_name", "other_name"),
    [("database", "postgres", "redis"), ("redis", "redis", "postgres")],
)
def test_single_disabled_subsystem_is_the_only_disabled_one(dependency_probes, disabled: str, check_name: str, other_name: str) -> None:
    _probes_return(dependency_probes, postgres={"reachable": True}, redis={"reachable": True})

    response = TestClient(create_app(AppFeatures(**{disabled: False}))).get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    expected = dict.fromkeys(SUBSYSTEMS, "enabled") | {disabled: "disabled"}
    assert payload["subsystems"] == expected
    assert payload["checks"][check_name] == _optional(_disabled_check(disabled))
    assert payload["checks"][other_name] == _optional({"reachable": True})
    probe = getattr(dependency_probes, check_name)
    assert probe.call_count == 0


@pytest.mark.parametrize("failing", ["postgres", "redis"])
def test_default_app_enabled_dependency_failure_still_fails_readiness(dependency_probes, failing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{failing.upper()}_REQUIRED", "true")
    failed = {"reachable": False, "error": "connection refused"}
    healthy = {"reachable": True}
    _probes_return(
        dependency_probes,
        postgres=failed if failing == "postgres" else healthy,
        redis=failed if failing == "redis" else healthy,
    )

    response = TestClient(create_app()).get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["subsystems"] == dict.fromkeys(SUBSYSTEMS, "enabled")
    assert payload["checks"][failing] == {**failed, "failure_stage": "connection_refused", "required": True}


def test_default_app_readiness_and_topology_schema_only_gain_subsystems(dependency_probes, monkeypatch: pytest.MonkeyPatch) -> None:
    _probes_return(dependency_probes, postgres={"reachable": True}, redis={"reachable": True})
    monkeypatch.setattr(redis_module, "redis", None)
    client = TestClient(create_app())

    readiness = client.get("/readyz").json()
    topology = client.get("/api/runtime/topology").json()

    assert set(readiness) == LEGACY_READINESS_KEYS | {"subsystems"}
    assert readiness["checks"] == {"postgres": _optional({"reachable": True}), "redis": _optional({"reachable": True})}
    assert readiness["subsystems"] == dict.fromkeys(SUBSYSTEMS, "enabled")
    assert set(topology["redis"]) == LEGACY_REDIS_TOPOLOGY_KEYS
    assert topology["redis"]["reason"] == "redis client not configured"
    assert topology["subsystems"] == dict.fromkeys(SUBSYSTEMS, "enabled")
    dependency_probes.postgres.assert_called_once()
    dependency_probes.redis.assert_awaited_once()


def test_mcp_route_does_not_shadow_frontend_assets() -> None:
    app = create_app(AppFeatures(database=False, observability=False, rag=False))
    client = TestClient(app)

    asset = client.get("/api/assets/api-runtime.js")
    missing = client.get("/api/assets/missing.js", headers={"Accept": "text/html"})

    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "no-store, max-age=0"
    assert asset.headers["pragma"] == "no-cache"
    assert missing.status_code == 404
    assert client.get("/unknown-path").json() == {"detail": "Not Found"}
