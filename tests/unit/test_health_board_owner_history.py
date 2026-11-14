"""OWNER last-known observations: isolated Redis and strict authorization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nabla.api import health_board_owner_history as history
from nabla.api import health_routes


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.key = ""
        self.mapping: dict[str, str] = {}
        self.ttl = 0

    def hset(self, key: str, *, mapping: dict[str, str]) -> FakePipeline:
        self.key = key
        self.mapping = mapping
        return self

    def expire(self, key: str, seconds: int) -> FakePipeline:
        assert key == self.key
        self.ttl = seconds
        return self

    async def execute(self) -> list[int]:
        assert self.ttl == 7 * 86400
        self.redis.rows.setdefault(self.key, {}).update(self.mapping)
        return [len(self.mapping), 1]


class FakeRedis:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, str]] = {}

    def pipeline(self, *, transaction: bool) -> FakePipeline:
        assert transaction is True
        return FakePipeline(self)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.rows.get(key, {}))


def _observed(seconds_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


@pytest.mark.asyncio
async def test_rotating_probes_keep_history_without_leaking_sensitive_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("HOMELAB_OWNER_HISTORY_REDIS_ENABLED", "true")
    monkeypatch.setenv("HOMELAB_OWNER_HISTORY_NAMESPACE", "cloud_test")
    monkeypatch.setattr(history, "resolve_redis_client", lambda: fake)
    sample = {
        "id": "gatus",
        "state": "warn",
        "probe_source": "origin",
        "probe_stale": False,
        "probe_observed_at": _observed(240),
        "url": "http://172.17.0.24:8085",
        "token": "never-write",
        "warning": "private details",
    }
    assert await history.write_owner_last_known({
        "homelab": {"services": [sample]},
    })
    assert await history.write_owner_last_known({
        "homelab": {
            "services": [{
                "id": "prometheus",
                "state": "ok",
                "probe_source": "origin",
                "probe_observed_at": _observed(360),
            }],
            "internal_services": [{
                "id": "gatus",
                "state": "fail",
                "probe_source": "origin",
                "probe_observed_at": _observed(370),
            }],
        },
    })
    stored = json.dumps(fake.rows)
    for secret in ("172.17.0.24", "never-write", "private details", "http://"):
        assert secret not in stored
    payload = await history.read_owner_last_known()
    assert payload["state"] == "historical"
    assert payload["current"] is False
    assert {(r["id"], r["scope"]) for r in payload["observations"]} == {
        ("gatus", "public"),
        ("gatus", "internal"),
        ("prometheus", "public"),
    }
    assert all(r["ageSeconds"] > 0 for r in payload["observations"])


@pytest.mark.asyncio
async def test_memory_stale_and_invalid_records_never_get_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOMELAB_OWNER_HISTORY_REDIS_ENABLED", "true")
    monkeypatch.setenv("HOMELAB_OWNER_HISTORY_NAMESPACE", "cloud_test")
    fake = FakeRedis()
    monkeypatch.setattr(history, "resolve_redis_client", lambda: fake)
    observations = [
        {"id": "cached", "state": "ok", "probe_source": "memory", "probe_observed_at": _observed()},
        {"id": "denied", "state": "fail", "probe_source": "deadline", "probe_observed_at": _observed()},
        {"id": "old", "state": "ok", "probe_source": "origin", "probe_observed_at": _observed(8 * 86400)},
        {"id": "private/key", "state": "ok", "probe_source": "origin", "probe_observed_at": _observed()},
    ]
    assert not await history.write_owner_last_known({"homelab": {"services": observations}})
    assert fake.rows == {}


@pytest.mark.asyncio
async def test_disabled_by_default_or_missing_namespace_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HOMELAB_OWNER_HISTORY_REDIS_ENABLED", raising=False)
    monkeypatch.delenv("HOMELAB_OWNER_HISTORY_NAMESPACE", raising=False)
    assert not await history.write_owner_last_known({"homelab": {}})
    assert (await history.read_owner_last_known())["state"] == "disabled"
    monkeypatch.setenv("HOMELAB_OWNER_HISTORY_REDIS_ENABLED", "true")
    assert (await history.read_owner_last_known())["state"] == "disabled"


def test_owner_last_known_endpoint_blocks_anonymous_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(health_routes, "owner_ui_authenticated", lambda *_: False)
    app = FastAPI()
    health_routes._register_health_board_routes(app)
    with TestClient(app) as client:
        response = client.get("/api/health-board/last-known")
    assert response.status_code == 403
    assert response.headers["cache-control"].startswith("no-store")
    assert "observations" not in response.text


def test_owner_last_known_endpoint_requires_verified_owner_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(health_routes, "owner_ui_authenticated", lambda *_: True)

    async def cached() -> dict:
        return {"state": "historical", "current": False, "observations": []}

    monkeypatch.setattr(history, "read_owner_last_known", cached)
    app = FastAPI()
    health_routes._register_health_board_routes(app)
    with TestClient(app) as client:
        response = client.get("/api/health-board/last-known")
    assert response.status_code == 200
    assert response.json()["state"] == "historical"
    assert response.headers["cache-control"].startswith("no-store")
