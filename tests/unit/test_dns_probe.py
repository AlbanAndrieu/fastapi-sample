"""Regression tests for bounded per-service DNS evidence."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import dns.resolver
import pytest

from nabla.api import dns_probe


class _Answers:
    def __init__(self, *addresses: str) -> None:
        self._addresses = addresses

    def addresses(self):
        return iter(self._addresses)


def _resolver(*, addresses=(), error: BaseException | None = None):
    resolve_name = (
        AsyncMock(side_effect=error)
        if error is not None
        else AsyncMock(return_value=_Answers(*addresses))
    )
    return SimpleNamespace(
        nameservers=[
            SimpleNamespace(address="172.17.0.1"),
            SimpleNamespace(address="1.1.1.1"),
        ],
        resolve_name=resolve_name,
    )


def test_system_dns_resolvers_uses_dnspython_resolver_configuration() -> None:
    resolver = _resolver()

    assert dns_probe.system_dns_resolvers(resolver) == (
        "172.17.0.1",
        "1.1.1.1 (Cloudflare DNS)",
    )


def test_resolver_display_identifies_known_public_and_docker_dns() -> None:
    assert dns_probe._resolver_display("127.0.0.11") == (
        "127.0.0.11 (Docker embedded DNS)"
    )
    assert dns_probe._resolver_display("1.1.1.1") == "1.1.1.1 (Cloudflare DNS)"
    assert dns_probe._resolver_display("9.9.9.9") == "9.9.9.9 (Quad9)"
    assert dns_probe._resolver_display("172.17.0.1") == "172.17.0.1"


@pytest.mark.asyncio
async def test_probe_dns_hostname_reports_resolver_latency_and_answers(
    monkeypatch,
) -> None:
    resolver = _resolver(addresses=("192.0.2.10", "2001:db8::10"))
    monkeypatch.setattr(dns_probe, "_resolver", lambda: resolver)

    result = await dns_probe.probe_dns_hostname("sample.example")

    resolver.resolve_name.assert_awaited_once_with(
        "sample.example",
        family=socket.AF_UNSPEC,
        lifetime=1.5,
        raise_on_no_answer=False,
    )
    assert result["dns_state"] == "ok"
    assert result["dns_hostname"] == "sample.example"
    assert result["dns_probe"] == "dnspython.resolve_name"
    assert result["dns_resolvers"] == [
        "172.17.0.1",
        "1.1.1.1 (Cloudflare DNS)",
    ]
    assert result["dns_resolver_source"] == "system"
    assert result["dns_resolved"] == ["192.0.2.10", "2001:db8::10"]
    assert isinstance(result["dns_latency_ms"], int)


@pytest.mark.asyncio
async def test_probe_dns_hostname_preserves_nxdomain_evidence(monkeypatch) -> None:
    resolver = _resolver(error=dns.resolver.NXDOMAIN())
    monkeypatch.setattr(dns_probe, "_resolver", lambda: resolver)

    result = await dns_probe.probe_dns_hostname("missing.example")

    assert result["dns_state"] == "fail"
    assert result["dns_resolved"] == []
    assert "does not exist" in result["dns_error"]
    assert result["dns_resolvers"] == [
        "172.17.0.1",
        "1.1.1.1 (Cloudflare DNS)",
    ]
