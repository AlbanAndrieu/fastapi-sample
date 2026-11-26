"""Hermetic, no-network contracts for the Cloud public light HTTP sampler."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from nabla.api import public_status_light as light


@pytest.fixture(autouse=True)
def reset() -> None:
    light.reset_light_public_checks()
    yield
    light.reset_light_public_checks()


def route(host: str, *, access: bool = False, visibility: bool = True):
    return SimpleNamespace(
        public=visibility,
        access_required=access,
        lifecycle="active",
        protocol="HTTPS",
        port=443,
        public_https_probe_url="https://" + host + "/health",
    )


def test_only_reviewed_public_https_is_eligible():
    assert light._approved_url(route("gatus.albandrieu.com"))
    assert light._approved_url(route("www.bababou.com"))
    assert light._approved_url(route("freshrss.albandrieu.com", access=True)) is None
    assert light._approved_url(route("redis.int.albandrieu.com")) is None
    assert light._approved_url(route("login.albandrieu.com")) is None
    assert light._approved_url(route("attacker.example.com")) is None
    assert light._approved_url(route("gatus.albandrieu.com", visibility=False)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (200, "ok"),
        (204, "ok"),
        (302, "unknown"),
        (401, "unknown"),
        (403, "unknown"),
        (429, "unknown"),
        (404, "fail"),
        (502, "fail"),
        (503, "fail"),
    ],
)
async def test_minimal_head_verdicts_do_not_confuse_access_with_health(monkeypatch, code, expected):
    async def dns(*_args, **_kwargs):
        return {"dns_state": "ok", "dns_resolved": ["93.184.215.14"]}

    monkeypatch.setattr(light, "probe_dns_hostname", dns)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(code, headers={"location": "https://elsewhere.invalid"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        assert await light._checked_status(client, "https://gatus.albandrieu.com/health") == expected
    assert len(requests) == 1
    assert requests[0].method == "HEAD"
    assert "authorization" not in requests[0].headers


@pytest.mark.asyncio
async def test_rejects_non_global_dns_without_any_http(monkeypatch):
    async def dns(*_args, **_kwargs):
        return {"dns_state": "ok", "dns_resolved": ["172.17.0.24"]}

    monkeypatch.setattr(light, "probe_dns_hostname", dns)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await light._checked_status(client, "https://gatus.albandrieu.com/") == "unknown"
    assert calls == []


def test_evidence_is_revision_bound_and_expires(monkeypatch):
    revision = "sha256:" + "a" * 64
    light._revision = revision
    light._samples["component:default/gatus"] = (100.0, "ok")
    monkeypatch.setattr(light.time, "monotonic", lambda: 101.0)
    assert light.fresh_public_states(revision) == {"component:default/gatus": "ok"}
    assert light.fresh_public_states("sha256:" + "b" * 64) == {}
    monkeypatch.setattr(light.time, "monotonic", lambda: 100.0 + light.MAX_AGE_SECONDS)
    assert light.fresh_public_states(revision) == {}


@pytest.mark.asyncio
async def test_scheduler_is_single_flight_and_bounded(monkeypatch):
    revision = "sha256:" + "a" * 64
    targets = [(f"component:default/s{i}", f"https://s{i}.albandrieu.com/") for i in range(20)]
    monkeypatch.setattr(light, "_targets", lambda raw: targets)
    batches = []
    release = asyncio.Event()

    async def wave(rows):
        batches.append(rows)
        await release.wait()

    monkeypatch.setattr(light, "_run_wave", wave)
    light.start_light_public_checks(revision, {"catalogRevision": revision})
    light.start_light_public_checks(revision, {"catalogRevision": revision})
    await asyncio.sleep(0)
    assert len(batches) == 1
    assert len(batches[0]) == light.MAX_WAVE
    release.set()
    await asyncio.sleep(0)
