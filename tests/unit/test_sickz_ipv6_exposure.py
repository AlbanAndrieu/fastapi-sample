"""Tests for the IPv6 negative-exposure probe of /sickz."""

import asyncio
import ssl

import httpx

from nabla.api import sickz_ipv6_exposure as ipv6


def test_parse_keeps_only_global_ipv6_pairs() -> None:
    raw = "ws=2606:4700:4700::1111, lan=fe80::1, ula=fd00::1, v4=172.17.0.57, junk, nas = 2001:4860:4860::8888"
    assert ipv6.parse_ipv6_targets(raw) == {"ws": "2606:4700:4700::1111", "nas": "2001:4860:4860::8888"}


def test_without_targets_reports_not_configured() -> None:
    assert asyncio.run(ipv6.probe_ipv6_exposure(""))["status"] == "not_configured"


def test_without_ipv6_egress_never_claims_not_exposed(monkeypatch) -> None:
    async def no_egress() -> bool:
        return False

    monkeypatch.setattr(ipv6, "_ipv6_egress_available", no_egress)
    result = asyncio.run(ipv6.probe_ipv6_exposure("ws=2606:4700:4700::1111"))
    assert result["status"] == "unknown"


def test_any_answering_port_marks_exposed(monkeypatch) -> None:
    async def egress() -> bool:
        return True

    async def answers(address: str, port: int) -> bool:
        return port == 8087

    monkeypatch.setattr(ipv6, "_ipv6_egress_available", egress)
    monkeypatch.setattr(ipv6, "_http_answers", answers)
    result = asyncio.run(ipv6.probe_ipv6_exposure("ws=2606:4700:4700::1111"))
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
    assert asyncio.run(ipv6.probe_ipv6_exposure("ws=2606:4700:4700::1111"))["status"] == "not_exposed"


def test_tls_certificate_error_counts_as_answering(monkeypatch) -> None:
    class FailingClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def head(self, url: str, **kwargs):
            try:
                raise ssl.SSLCertVerificationError("hostname mismatch")
            except ssl.SSLError as cause:
                raise httpx.ConnectError("certificate verify failed") from cause

    monkeypatch.setattr(ipv6.httpx, "AsyncClient", FailingClient)
    assert asyncio.run(ipv6._http_answers("2606:4700:4700::1111", 443)) is True


def test_refuses_unbounded_targets_or_overwritten_labels() -> None:
    targets = ",".join(f"node{i}=2606:4700:4700::{i + 1}" for i in range(7))
    assert asyncio.run(ipv6.probe_ipv6_exposure(targets))["status"] == "unknown"
    assert asyncio.run(ipv6.probe_ipv6_exposure("x=" + "a" * 3000))["status"] == "unknown"
    assert asyncio.run(ipv6.probe_ipv6_exposure("node=2606:4700:4700::1,node=2606:4700:4700::2"))["status"] == "unknown"
    assert ipv6.parse_ipv6_targets("invalid.label=2606:4700:4700::1,valid=2606:4700:4700::2") == {"valid": "2606:4700:4700::2"}


def test_direct_ipv6_probes_ignore_system_proxies_and_use_head(monkeypatch) -> None:
    observed = []

    class ProbeClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs.get("follow_redirects") is not True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def head(self, url, **_kwargs):
            observed.append(url)
            return httpx.Response(405)

    monkeypatch.setattr(ipv6.httpx, "AsyncClient", ProbeClient)
    assert asyncio.run(ipv6._ipv6_egress_available()) is True
    assert asyncio.run(ipv6._http_answers("2606:4700:4700::1111", 443)) is True
    assert observed == [
        "https://ipv6.google.com/",
        "https://[2606:4700:4700::1111]:443/",
    ]
