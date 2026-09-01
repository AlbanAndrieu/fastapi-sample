"""Regression tests for distinct TrueNAS TCP/TLS diagnostics."""

from __future__ import annotations

import pytest

from nabla.api import truenas_transport_diagnostics as transport


class _RawSocket:
    def settimeout(self, _timeout: float) -> None:
        return None

    def close(self) -> None:
        return None


class _TlsSocket:
    def settimeout(self, _timeout: float) -> None:
        return None

    def do_handshake(self) -> None:
        return None

    def cipher(self):
        return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

    def version(self) -> str:
        return "TLSv1.3"

    def getpeercert(self):
        return {
            "subject": ((('commonName', '*.albandrieu.com'),),),
            "issuer": ((('commonName', 'YR2'),),),
            "notAfter": "Nov 15 00:20:42 2026 GMT",
        }

    def close(self) -> None:
        return None


class _TlsContext:
    check_hostname = True
    verify_mode = 2

    def wrap_socket(self, _socket, **_kwargs):
        return _TlsSocket()


@pytest.mark.asyncio
async def test_tcp_timeout_blocks_tls_without_claiming_tls_timeout(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(transport.socket, "create_connection", timeout)

    tcp, tls, reachable = await transport.collect_tcp_tls_stages(
        "truenas.albandrieu.com", 7000, True
    )

    assert reachable is False
    assert tcp["label"] == "TCP connect"
    assert tcp["state"] == "fail"
    assert tcp["failure_stage"] == "tcp_connect"
    assert tls["state"] == "blocked"
    assert tls["failure_stage"] == "tcp_connect"
    assert "TLS was not attempted" in tls["detail"]
    assert "elapsed_ms" not in tls


@pytest.mark.asyncio
async def test_tls_success_exposes_verified_certificate_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        transport.socket,
        "create_connection",
        lambda *_args, **_kwargs: _RawSocket(),
    )
    monkeypatch.setattr(transport.ssl, "create_default_context", _TlsContext)

    tcp, tls, reachable = await transport.collect_tcp_tls_stages(
        "truenas.albandrieu.com", 7000, True
    )

    assert reachable is True
    assert tcp["state"] == "ok"
    assert tls["state"] == "ok"
    assert tls["tls_version"] == "TLSv1.3"
    assert tls["cipher"] == "TLS_AES_256_GCM_SHA384"
    assert tls["certificate_verified"] is True
    assert tls["hostname_verified"] is True
    assert tls["certificate_subject_cn"] == "*.albandrieu.com"
    assert tls["certificate_issuer_cn"] == "YR2"
    assert tls["certificate_not_after"].startswith("2026-11-15")
    assert "Certificate trusted" in tls["detail"]


def test_wan_metadata_defaults_to_free_static_ipv4(monkeypatch) -> None:
    monkeypatch.delenv("HOMELAB_WAN_IPV4", raising=False)
    monkeypatch.delenv("HOMELAB_WAN_PROVIDER", raising=False)

    assert transport.homelab_wan_metadata() == {
        "ipv4": "82.66.4.247",
        "provider": "Free",
        "static": True,
    }
