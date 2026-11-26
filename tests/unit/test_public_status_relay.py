"""Closed-schema service state relay: no private labels, replay or stale green."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from nabla.api import public_status_relay as relay
from nabla.route_policy import Credential, Visibility, route_policy_for

SECRET = "f" * 32
NOW = datetime.now(timezone.utc)
REVISION = "sha256:" + "b" * 64


def test_projection_sends_only_proven_minimal_states():
    payload = {
        "services": [
            {"id": "gatus", "state": "ok", "probe_source": "origin", "probe_age_seconds": 2, "probe_stale_after_seconds": 120, "url": "https://172.17.0.24"},
            {"id": "missing", "state": "fail", "probe_stale": True, "probe_source": "origin", "probe_age_seconds": 2, "probe_stale_after_seconds": 120},
            {"id": "unauthenticated", "state": "warn", "probe_source": "deadline", "probe_age_seconds": 2, "probe_stale_after_seconds": 120},
        ],
        "internal_services": [
            {"id": "gatus", "state": "ok", "probe_source": "memory", "probe_age_seconds": 5, "probe_stale_after_seconds": 120, "host": "192.168.1.5"},
        ],
    }
    rows = relay.project_rows(payload)
    assert rows == [{"id": "gatus", "state": "ok", "age": 5}]
    assert "172.17" not in json.dumps(rows) and "192.168" not in json.dumps(rows)


def test_schema_rejects_leaks_duplicates_stale_and_bad_states():
    data = relay.build_payload(REVISION, [{"id": "gatus", "state": "ok", "age": 1}], now=NOW)
    assert relay.validate(data, now=NOW) == data
    for candidate in (
        {**data, "ip": "192.168.1.1"},
        {**data, "catalogRevision": "sha256:xyz"},
        {**data, "services": [{"id": "gatus", "state": "green", "age": 1}]},
        {**data, "services": [{"id": "gatus", "state": "ok", "age": True}]},
        {**data, "services": [{"id": "gatus", "state": [], "age": 1}]},
        {**data, "v": True},
        {**data, "services": data["services"] * 2},
        {**data, "observed_at": relay._iso(NOW - timedelta(minutes=8))},
    ):
        assert relay.validate(candidate, now=NOW) is None
    assert relay.validate(data, now=NOW + timedelta(seconds=relay.TTL)) is None


def test_hmac_receiver_requires_optin_identity_and_valid_signature(monkeypatch):
    monkeypatch.setenv("TRUENAS_SERVICE_STATUS_RELAY_ENABLED", "true")
    monkeypatch.setattr(relay, "get_settings", lambda: SimpleNamespace(truenas_federation_secret=SecretStr(SECRET)))
    monkeypatch.setattr(relay, "fastapi_cloud_runtime_detected", lambda _host=None: True)
    monkeypatch.setattr(relay, "_redis", _no_redis)
    relay._received = None
    app = FastAPI()
    relay.register_routes(app)
    client = TestClient(app)
    raw = json.dumps(relay.build_payload(REVISION, [{"id": "gatus", "state": "ok", "age": 1}], now=datetime.now(timezone.utc))).encode()
    headers = {relay.HEADER: relay.sign(raw, SECRET), "content-type": "application/json"}
    assert client.post(relay.PATH, content=raw, headers=headers).status_code == 202
    assert client.post(relay.PATH, content=raw, headers=headers).status_code == 409
    assert client.post(relay.PATH, content=raw, headers={relay.HEADER: relay.sign(raw, "g" * 32), "content-type": "application/json"}).status_code == 401
    assert client.post(relay.PATH, content=b"x" * (relay.MAX_BODY + 1), headers=headers).status_code == 413
    monkeypatch.setenv("TRUENAS_SERVICE_STATUS_RELAY_ENABLED", "false")
    assert client.post(relay.PATH, content=raw, headers=headers).status_code == 404
    relay._received = None


async def _no_redis():
    return None


@pytest.mark.asyncio
async def test_read_states_is_revision_bound_and_expiring(monkeypatch):
    monkeypatch.setattr(relay, "_redis", _no_redis)
    relay._received = relay.build_payload(REVISION, [{"id": "gatus", "state": "ok", "age": 2}], now=datetime.now(timezone.utc))
    assert await relay.read_states(REVISION) == {"gatus": "ok"}
    assert await relay.read_states("sha256:" + "a" * 64) == {}
    relay._received = None


def test_route_never_falls_through_to_review():
    p = route_policy_for("/federation/services", method="POST")
    assert (p.visibility, p.credential) == (Visibility.SERVICE, Credential.FEDERATION_HMAC)
    assert route_policy_for("/federation/services", method="GET").visibility == Visibility.REVIEW
