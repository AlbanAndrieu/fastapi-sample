"""Tests for bounded public egress observation."""

import httpx
import pytest

from nabla.api import public_egress_observer


def test_parse_public_ip_accepts_only_global_literals() -> None:
    assert public_egress_observer._parse_public_ip("34.200.20.162\n") == "34.200.20.162"
    assert public_egress_observer._parse_public_ip("172.17.0.24") is None
    assert public_egress_observer._parse_public_ip("not-an-ip") is None


@pytest.mark.asyncio
async def test_observer_caches_successful_egress(monkeypatch) -> None:
    public_egress_observer._cache.clear()
    public_egress_observer._cache.update({"ip": None, "observed_at": 0.0})
    calls = 0

    async def fake_fetch() -> str:
        nonlocal calls
        calls += 1
        return "34.200.20.162"

    monkeypatch.setattr(public_egress_observer, "_fetch_public_egress_ip", fake_fetch)

    first = await public_egress_observer.observe_public_egress_ip()
    second = await public_egress_observer.observe_public_egress_ip()

    assert first["ip"] == "34.200.20.162"
    assert first["cached"] is False
    assert second["ip"] == "34.200.20.162"
    assert second["cached"] is True
    assert calls == 1


@pytest.mark.asyncio
async def test_observer_soft_fails_when_echo_is_unavailable(monkeypatch) -> None:
    public_egress_observer._cache.clear()
    public_egress_observer._cache.update({"ip": None, "observed_at": 0.0})

    async def fake_fetch() -> str:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(public_egress_observer, "_fetch_public_egress_ip", fake_fetch)

    result = await public_egress_observer.observe_public_egress_ip()

    assert result == {
        "ip": None,
        "observed": False,
        "cached": False,
        "source": "external_echo",
    }
