"""Tests for the IPv6 negative-exposure probe of /sickz."""

import asyncio
import ssl

import httpx

from nabla.api import sickz_ipv6_exposure as ipv6


def test_parse_keeps_only_global_ipv6_pairs() -> None:
    raw = "ws=2a01:e0a:a17:3c01::10, lan=fe80::1, ula=fd00::1, v4=172.17.0.57, junk, nas = 2a01:e0a:a17:3c01::24"
    assert ipv6.parse_ipv6_targets(raw) == {"ws": "2a01:e0a:a17:3c01::10", "nas": "2a01:e0a:a17:3c01::24"}


def test_without_targets_reports_not_configured() -> None:
    assert asyncio.run(ipv6.probe_ipv6_exposure(""))["status"] == "not_configured"


def test_without_ipv6_egress_never_claims_not_exposed(monkeypatch) -> None:
    async def no_egress() -> bool:
        return False

    monkeypatch.setattr(ipv6, "_ipv6_egress_available", no_egress)
    result = asyncio.run(ipv6.probe_ipv6_exposure("ws=2a01:e0a:a17:3c01::10"))
    assert result["status"] == "unknown"


def test_any_answering_port_marks_exposed(monkeypatch) -> None:
    async def egress() -> bool:
        return True

    async def answers(address: str, port: int) -> bool:
        return port == 8087

    monkeypatch.setattr(ipv6, "_ipv6_egress_available", egress)
    monkeypatch.setattr(ipv6, "_http_answers", answers)
    result = asyncio.run(ipv6.probe_ipv6_exposure("ws=2a01:e0a:a17:3c01::10"))
    assert result["status"] == "exposed"
    assert result["ports"]["ws"]["8087"] is True
    assert result["ports"]["ws"]["11434"] is False


def test_all_closed_is_not_exposed(monkeypatch) -> None:
    async def egress() -> bool:
        return True

    async def closed(address: str, port: int) -> bool:
        return False

    monkeypatch.setattr(ipv6, "_ipv6_egress_available", egress)
    monkeypatch.setattr(ipv6, "_http_answers", closed)
    assert asyncio.run(ipv6.probe_ipv6_exposure("ws=2a01:e0a:a17:3c01::10"))["status"] == "not_exposed"


def test_tls_certificate_error_counts_as_answering(monkeypatch) -> None:
    class FailingClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def get(self, url: str, **kwargs):
            try:
                raise ssl.SSLCertVerificationError("hostname mismatch")
            except ssl.SSLError as cause:
                raise httpx.ConnectError("certificate verify failed") from cause

    monkeypatch.setattr(ipv6.httpx, "AsyncClient", FailingClient)
    assert asyncio.run(ipv6._http_answers("2a01:e0a:a17:3c01::10", 443)) is True
