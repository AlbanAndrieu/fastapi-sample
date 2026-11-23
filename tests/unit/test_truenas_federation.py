"""Signed TrueNAS -> FastAPI Cloud evidence relay (offline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
from pydantic import SecretStr
import pytest
from starlette.testclient import TestClient

from nabla.api import truenas_federation as federation
from nabla.route_policy import Credential, Visibility, route_policy_for

SECRET = "f" * 32
NOW = datetime(2026, 11, 22, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def relay(monkeypatch):
    settings = SimpleNamespace(truenas_federation_secret=SecretStr(SECRET), truenas_federation_cloud_url="https://fastapi-sample.fastapicloud.dev")
    monkeypatch.setattr(federation, "get_settings", lambda: settings)
    monkeypatch.setattr(federation, "fastapi_cloud_runtime_detected", lambda _host=None: True)
    federation._received.clear()
    federation._push_state["last"] = 0.0
    app = FastAPI()
    federation.register_truenas_federation_routes(app)
    yield settings, TestClient(app)
    federation._received.clear()


def _post(client, payload, *, secret=SECRET, signature=None):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"content-type": "application/json", federation.SIGNATURE_HEADER: signature or federation.sign(raw, secret)}
    return client.post(federation.PATH, content=raw, headers=headers)


def test_aggregate_is_closed_dated_and_bounded() -> None:
    aggregate = federation.build_aggregate({"reachable": False, "stage": "auth failed: 10.0.0.1"}, now=NOW)
    assert set(aggregate) == federation._KEYS
    assert (aggregate["truenas_api"], aggregate["stage"]) == ("fail", "other")
    assert federation.validate_aggregate(aggregate, now=NOW) == aggregate
    for broken in (
        {**aggregate, "host": "172.17.0.24"},
        {**aggregate, "truenas_api": "green"},
        {**aggregate, "observed_at": "2026-11-22T20:05:00Z"},
        {**aggregate, "expires_at": "2026-11-22T21:00:00Z"},
        {**aggregate, "expires_at": "2026-11-22T19:59:00Z"},
    ):
        assert federation.validate_aggregate(broken, now=NOW) is None
    assert federation.validate_aggregate(aggregate, now=NOW + timedelta(seconds=federation.TTL_SECONDS)) is None


def test_receiver_accepts_once_rejects_replay_and_never_rolls_back(relay) -> None:
    _settings, client = relay
    now = datetime.now(timezone.utc)
    aggregate = federation.build_aggregate({"reachable": True, "stage": "ok"}, now=now)

    assert _post(client, aggregate).status_code == 202
    assert _post(client, aggregate).status_code == 409
    older = federation.build_aggregate({"reachable": False, "stage": "ok"}, now=now - timedelta(seconds=30))
    assert _post(client, older).status_code == 409

    evidence = federation.relayed_truenas_evidence()
    assert evidence["source"] == "truenas_lan_relay" and evidence["truenas_api"] == "ok"
    assert federation.relayed_truenas_evidence(now + timedelta(seconds=federation.TTL_SECONDS)) is None


def test_receiver_denies_bad_signature_schema_size_and_disabled_states(relay, monkeypatch) -> None:
    settings, client = relay
    aggregate = federation.build_aggregate({"reachable": True}, now=datetime.now(timezone.utc))

    assert _post(client, aggregate, secret="g" * 32).status_code == 401
    assert _post(client, aggregate, signature="sha1=abc").status_code == 401
    assert _post(client, {**aggregate, "ip": "10.0.0.1"}).status_code == 422
    huge = client.post(
        federation.PATH,
        content=b"x" * (federation.MAX_BODY + 1),
        headers={"content-type": "application/json", federation.SIGNATURE_HEADER: "sha256=" + "0" * 64},
    )
    assert huge.status_code == 413
    assert federation._received == {}

    monkeypatch.setattr(federation, "fastapi_cloud_runtime_detected", lambda _host=None: False)
    assert _post(client, aggregate).status_code == 404
    settings.truenas_federation_secret = SecretStr("short")
    monkeypatch.setattr(federation, "fastapi_cloud_runtime_detected", lambda _host=None: True)
    assert _post(client, aggregate).status_code == 404


@pytest.mark.asyncio
async def test_producer_is_homelab_only_signed_and_throttled(relay, monkeypatch) -> None:
    settings, _client = relay
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(federation, "homelab_runtime_detected", lambda: False)
    assert await federation.push_truenas_aggregate({"reachable": True}, transport=transport) == "disabled"

    monkeypatch.setattr(federation, "homelab_runtime_detected", lambda: True)
    assert await federation.push_truenas_aggregate({"reachable": True}, transport=transport) == "sent"
    assert await federation.push_truenas_aggregate({"reachable": True}, transport=transport) == "throttled"
    request = sent[0]
    assert str(request.url) == "https://fastapi-sample.fastapicloud.dev/federation/truenas"
    assert request.headers[federation.SIGNATURE_HEADER] == federation.sign(request.content, SECRET)
    assert "172.17" not in request.content.decode()

    settings.truenas_federation_cloud_url = "http://insecure.example"
    federation._push_state["last"] = 0.0
    assert await federation.push_truenas_aggregate({"reachable": True}, transport=transport) == "disabled"


def test_route_is_a_signed_service_ingestion_not_review() -> None:
    policy = route_policy_for("/federation/truenas", method="POST")
    assert (policy.visibility, policy.credential) == (Visibility.SERVICE, Credential.FEDERATION_HMAC)
    assert route_policy_for("/federation/truenas", method="GET").visibility is Visibility.REVIEW
