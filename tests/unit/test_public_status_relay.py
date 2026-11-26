"""Closed-schema service state relay: no private labels, replay or stale green."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from pydantic import SecretStr
import pytest

from nabla import lifespan
from nabla.api import public_status_relay as relay
from nabla.route_policy import Credential, Visibility, route_policy_for

SECRET = "f" * 32
NOW = datetime.now(timezone.utc)
REVISION = "sha256:" + "b" * 64


def _entity(name, title, kind="Component"):
    return SimpleNamespace(kind=kind, metadata=SimpleNamespace(name=name, title=title))


CATALOG = SimpleNamespace(
    catalogRevision=REVISION,
    entities=[
        _entity("gatus", "Gatus"),
        _entity("immich", "Immich"),
        _entity("redis-a", "Redis"),
        _entity("redis-b", "Redis"),
        _entity("grafana", "Grafana"),
        _entity("owners", "Owners", kind="Group"),
    ],
)


def _view(services, **overrides):
    return {
        "schemaVersion": 2,
        "model": "public-service-overview",
        "catalogRevision": REVISION,
        "boardState": "fresh",
        "catalogSource": "backstage-v2",
        "services": services,
        **overrides,
    }


def test_public_view_rows_relay_only_fresh_unique_reviewed_names():
    services = [
        {"name": "Gatus", "kind": "Component", "state": "ok"},
        {"name": "Immich", "kind": "Component", "state": "fail"},
        {"name": "Redis", "kind": "Component", "state": "ok"},  # two entities share the title
        {"name": "Grafana", "kind": "Component", "state": "unknown"},  # receiver default
        {"name": "Owners", "kind": "Component", "state": "ok"},  # not a service kind
        {"name": "Elsewhere", "kind": "Component", "state": "ok"},  # not in the catalog
    ]
    assert relay.public_view_rows(_view(services), CATALOG) == [
        {"id": "gatus", "state": "ok", "age": 0},
        {"id": "immich", "state": "fail", "age": 0},
    ]
    for rejected in (
        _view(services, boardState="stale"),
        _view(services, catalogSource="bootstrap-snapshot"),
        _view(services, catalogRevision="sha256:" + "a" * 64),
        _view("not-a-list"),
        None,
    ):
        assert relay.public_view_rows(rejected, CATALOG) == []


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


def test_send_budget_is_spaced_and_capped(monkeypatch):
    """Hobby scales to zero: whatever triggers it, TrueNAS cannot keep Cloud awake."""
    monkeypatch.setattr(relay, "_sent_at", relay.deque())

    def send(now):
        due = relay.send_due(now)
        if due:
            relay._sent_at.append(now)
        return due

    assert send(0.0)
    assert not send(relay._MIN_GAP - 1)
    assert send(relay._MIN_GAP)
    # One rolling day of attempts every _MIN_GAP still sends at most the daily cap.
    assert sum(send(10_000.0 + i * relay._MIN_GAP) for i in range(int(86400 // relay._MIN_GAP))) <= relay._DAILY_SENDS
    assert 2 * len(relay.WAKE_HOURS) <= relay._DAILY_SENDS  # every slot keeps its retry


@pytest.mark.asyncio
async def test_send_signs_public_rows_and_reports_cloud_acceptance(monkeypatch):
    monkeypatch.setattr(relay, "enabled_producer", lambda: True)
    monkeypatch.setattr(relay, "_secret", lambda: SECRET)
    monkeypatch.setattr(relay, "_sent_at", relay.deque())
    monkeypatch.setattr(relay, "get_settings", lambda: SimpleNamespace(truenas_federation_cloud_url="https://fastapi-sample.fastapicloud.dev"))
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(202)

    rows = [{"id": "gatus", "state": "ok", "age": 0}]
    transport = httpx.MockTransport(handler)
    assert await relay.send([], REVISION, transport=transport) == "no_evidence"
    assert await relay.send(rows, REVISION, transport=transport) == "sent"
    assert await relay.send(rows, REVISION, transport=transport) == "budget"  # spaced by _MIN_GAP
    assert len(seen) == 1
    request = seen[0]
    assert (request.method, request.url.host, request.url.path) == ("POST", "fastapi-sample.fastapicloud.dev", relay.PATH)
    assert request.headers[relay.HEADER] == relay.sign(request.content, SECRET)
    body = json.loads(request.content)
    assert (body["catalogRevision"], body["services"]) == (REVISION, rows)


@pytest.mark.asyncio
async def test_local_public_view_waits_for_a_fresh_board_in_process(monkeypatch):
    monkeypatch.setattr(relay, "_VIEW_RETRY_SECONDS", 0.0)
    boards = iter(["pending", "stale", "fresh"])
    app = FastAPI()

    @app.get("/api/ui/services")
    def view():
        return _view([], boardState=next(boards))

    assert (await relay._local_public_view(app))["boardState"] == "fresh"
    never = FastAPI()

    @never.get("/api/ui/services")
    def stale():
        return _view([], boardState="stale")

    assert await relay._local_public_view(never) is None


PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 26, 6, 59, tzinfo=timezone.utc), datetime(2026, 11, 26, 8, tzinfo=PARIS)),
        (datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc), datetime(2026, 11, 26, 12, tzinfo=PARIS)),  # 08:00 is past
        (datetime(2026, 11, 26, 13, 0, tzinfo=timezone.utc), datetime(2026, 11, 26, 18, tzinfo=PARIS)),
        (datetime(2026, 11, 26, 17, 30, tzinfo=timezone.utc), datetime(2026, 11, 26, 21, tzinfo=PARIS)),
        (datetime(2026, 11, 26, 20, 30, tzinfo=timezone.utc), datetime(2026, 11, 27, 8, tzinfo=PARIS)),
        (datetime(2026, 7, 1, 5, 59, tzinfo=timezone.utc), datetime(2026, 7, 1, 8, tzinfo=PARIS)),  # CEST
    ],
)
def test_wake_slots_follow_paris_wall_clock(now, expected):
    slot = relay.next_wake(now)
    assert slot == expected
    assert (slot.astimezone(PARIS).hour, slot.astimezone(PARIS).minute) == (expected.hour, 0)


def test_relayed_states_outlive_the_longest_gap_between_slots():
    slot = relay.next_wake(datetime(2026, 1, 1, tzinfo=timezone.utc))
    gaps = []
    while slot.year == 2026:
        following = relay.next_wake(slot)
        # Same-tzinfo subtraction is wall-clock; compare real instants in UTC.
        gaps.append((following.astimezone(timezone.utc) - slot.astimezone(timezone.utc)).total_seconds())
        slot = following
    # 21:00 -> 08:00 lasts 12 h on the autumn DST night.
    assert max(gaps) == 12 * 3600
    assert max(gaps) + 1800 <= relay.TTL
    assert len(relay.WAKE_HOURS) <= relay._DAILY_SENDS


@pytest.mark.asyncio
async def test_wake_loop_retries_once_and_survives_errors(monkeypatch):
    outcomes = iter([RuntimeError("view failed"), "sent", asyncio.CancelledError()])
    calls = []

    async def wake_once(app):
        calls.append(app)
        outcome = next(outcomes)
        if isinstance(outcome, BaseException):
            raise outcome  # CancelledError stops the infinite clock
        return outcome

    monkeypatch.setattr(relay, "next_wake", lambda now: now)  # every slot is due now
    monkeypatch.setattr(relay, "_MIN_GAP", 0.0)
    monkeypatch.setattr(relay, "wake_once", wake_once)
    app = object()
    with pytest.raises(asyncio.CancelledError):
        await relay.run_wake_slots(app)
    # Slot 1: failure then retry succeeds; slot 2 starts afresh.
    assert calls == [app, app, app]


def test_wake_clock_starts_only_with_an_app_and_an_enabled_producer(monkeypatch):
    started = []

    def start(coroutine, *, name, tasks):
        coroutine.close()
        started.append(name)

    monkeypatch.setattr(lifespan, "cloud_background_workers_allowed", lambda: True)
    monkeypatch.setattr(lifespan, "_start_background_task", start)
    features = SimpleNamespace(observability=False)
    for enabled, app, expected in ((False, FastAPI(), []), (True, None, []), (True, FastAPI(), ["public-status-relay-wake-slots"])):
        monkeypatch.setattr(relay, "enabled_producer", lambda enabled=enabled: enabled)
        started.clear()
        lifespan._start_background_workers(features, None, [], app)
        assert started == expected


def test_route_never_falls_through_to_review():
    p = route_policy_for("/federation/services", method="POST")
    assert (p.visibility, p.credential) == (Visibility.SERVICE, Credential.FEDERATION_HMAC)
    assert route_policy_for("/federation/services", method="GET").visibility == Visibility.REVIEW
