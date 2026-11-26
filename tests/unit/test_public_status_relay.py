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
            {"id": "gatus", "state": "ok", "probe_source": "origin", "probe_age_seconds": 2, "probe_stale_after_seconds": 120, "http_status": 200, "url": "https://172.17.0.24"},
            {"id": "missing", "state": "fail", "probe_stale": True, "probe_source": "origin", "probe_age_seconds": 2, "probe_stale_after_seconds": 120},
            {"id": "unauthenticated", "state": "warn", "probe_source": "deadline", "probe_age_seconds": 2, "probe_stale_after_seconds": 120},
        ],
        "internal_services": [
            {"id": "gatus", "state": "ok", "probe_source": "memory", "probe_age_seconds": 5, "probe_stale_after_seconds": 120, "host": "192.168.1.5"},
        ],
    }
    rows = relay.project_rows(payload)
    assert rows == [{"id": "gatus", "state": "warn", "age": 5}]
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
    states, age = await relay.read_states(REVISION)
    assert states == {"gatus": "ok"}
    assert 0 <= age < relay.FRESH_SECONDS
    assert await relay.read_states("sha256:" + "a" * 64) == ({}, 0.0)
    relay._received = None


def test_send_budget_wakes_cloud_only_on_change_or_heartbeat(monkeypatch):
    """Hobby scales to zero: a steady TrueNAS must not keep Cloud awake."""
    monkeypatch.setattr(relay, "_sent_at", relay.deque())
    monkeypatch.setattr(relay, "_sent_fingerprint", None)

    def send(fingerprint, now):
        due = relay.send_due(fingerprint, now)
        if due:
            relay._sent_at.append(now)
            relay._remember(fingerprint)
        return due

    assert send("a", 0.0)
    assert not send("a", relay._CHECK_INTERVAL)  # unchanged
    assert not send("b", relay._MIN_GAP - 1)  # changed, but spaced
    assert send("b", relay._MIN_GAP)
    assert not send("b", relay._MIN_GAP + relay._HEARTBEAT - 1)
    assert send("b", relay._MIN_GAP + relay._HEARTBEAT)  # heartbeat refreshes TTL
    assert relay._HEARTBEAT < relay.TTL

    # A flapping service cannot exceed the rolling daily cap.
    sends = sum(send(str(i % 2), 10_000.0 + i * relay._MIN_GAP) for i in range(200))
    assert len(relay._sent_at) <= relay._DAILY_SENDS
    assert sends <= relay._DAILY_SENDS
    assert relay._DAILY_SENDS * relay._MIN_GAP <= 86400


def test_route_never_falls_through_to_review():
    p = route_policy_for("/federation/services", method="POST")
    assert (p.visibility, p.credential) == (Visibility.SERVICE, Credential.FEDERATION_HMAC)
    assert route_policy_for("/federation/services", method="GET").visibility == Visibility.REVIEW


def test_access_challenge_or_redirect_does_not_publish_app_green():
    examples = {
        "services": [
            {"id": "login", "state": "ok", "probe_source": "origin", "probe_age_seconds": 0, "probe_stale_after_seconds": 120, "http_status": 302},
            {"id": "gatus", "state": "ok", "probe_source": "origin", "probe_age_seconds": 0, "probe_stale_after_seconds": 120, "http_status": 200},
        ],
        "internal_services": [],
    }
    assert relay.project_rows(examples) == [{"id": "gatus", "state": "ok", "age": 0}]
