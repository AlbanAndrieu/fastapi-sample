"""TCP/TLS diagnostics for the public TrueNAS ingress path."""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any

_DIAGNOSTIC_TIMEOUT_SEC = 5.0
_DEFAULT_HOMELAB_WAN_IPV4 = "82.66.4.247"
_DEFAULT_HOMELAB_WAN_PROVIDER = "Free"


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def homelab_wan_metadata() -> dict[str, Any]:
    """Return the documented public homelab ingress identity."""
    ipv4 = os.getenv("HOMELAB_WAN_IPV4", _DEFAULT_HOMELAB_WAN_IPV4).strip()
    provider = os.getenv("HOMELAB_WAN_PROVIDER", _DEFAULT_HOMELAB_WAN_PROVIDER).strip()
    return {
        "ipv4": ipv4 or _DEFAULT_HOMELAB_WAN_IPV4,
        "provider": provider or _DEFAULT_HOMELAB_WAN_PROVIDER,
        "static": True,
    }


def _common_name(name: Any) -> str | None:
    for relative_distinguished_name in name or ():
        for key, value in relative_distinguished_name:
            if key == "commonName":
                return str(value)
    return None


def _certificate_metadata(
    tls_socket: ssl.SSLSocket,
    *,
    verify_ssl: bool,
) -> dict[str, Any]:
    certificate = tls_socket.getpeercert()
    metadata: dict[str, Any] = {
        "certificate_verified": verify_ssl,
        "hostname_verified": verify_ssl,
    }
    if not certificate:
        return metadata

    not_after_raw = certificate.get("notAfter")
    not_after: str | None = None
    days_remaining: int | None = None
    if isinstance(not_after_raw, str) and not_after_raw:
        try:
            expires_at = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(not_after_raw),
                timezone.utc,
            )
            not_after = expires_at.isoformat().replace("+00:00", "Z")
            days_remaining = max(
                0,
                (expires_at.date() - datetime.now(timezone.utc).date()).days,
            )
        except (TypeError, ValueError):
            not_after = not_after_raw

    metadata.update(
        {
            "certificate_subject_cn": _common_name(certificate.get("subject")),
            "certificate_issuer_cn": _common_name(certificate.get("issuer")),
            "certificate_not_after": not_after,
            "certificate_days_remaining": days_remaining,
        }
    )
    return {key: value for key, value in metadata.items() if value is not None}


def _tls_detail(verify_ssl: bool, metadata: dict[str, Any]) -> str:
    if not verify_ssl:
        return "TLS connected · certificate verification disabled"
    parts = ["Certificate trusted"]
    if metadata.get("certificate_subject_cn"):
        parts.append(str(metadata["certificate_subject_cn"]))
    if metadata.get("certificate_not_after"):
        expiry = str(metadata["certificate_not_after"]).split("T", maxsplit=1)[0]
        parts.append(f"expires {expiry}")
    return " · ".join(parts)


def _tcp_tls_probe(
    host: str,
    port: int,
    verify_ssl: bool,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Measure TCP connect and TLS handshake separately on the same socket."""
    raw_socket: socket.socket | None = None
    tls_socket: ssl.SSLSocket | None = None

    tcp_started = time.perf_counter()
    try:
        raw_socket = socket.create_connection(
            (host, port),
            timeout=_DIAGNOSTIC_TIMEOUT_SEC,
        )
    except (OSError, TimeoutError) as exc:
        error = (str(exc).strip() or exc.__class__.__name__)[:240]
        return (
            {
                "id": "socket",
                "label": "TCP connect",
                "state": "fail",
                "elapsed_ms": _elapsed_ms(tcp_started),
                "detail": error,
                "failure_stage": "tcp_connect",
            },
            {
                "id": "tls",
                "label": "TLS handshake",
                "state": "blocked",
                "detail": "Blocked by TCP connect failure; TLS was not attempted",
                "failure_stage": "tcp_connect",
            },
            False,
        )

    tcp_stage = {
        "id": "socket",
        "label": "TCP connect",
        "state": "ok",
        "elapsed_ms": _elapsed_ms(tcp_started),
        "detail": f"Connected to {host}:{port}",
    }

    context = ssl.create_default_context()
    if not verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    raw_socket.settimeout(_DIAGNOSTIC_TIMEOUT_SEC)
    tls_started = time.perf_counter()
    try:
        tls_socket = context.wrap_socket(
            raw_socket,
            server_hostname=host,
            do_handshake_on_connect=False,
        )
        raw_socket = None
        tls_socket.settimeout(_DIAGNOSTIC_TIMEOUT_SEC)
        tls_socket.do_handshake()
        cipher_info = tls_socket.cipher()
        metadata = _certificate_metadata(tls_socket, verify_ssl=verify_ssl)
        tls_stage = {
            "id": "tls",
            "label": "TLS handshake",
            "state": "ok",
            "elapsed_ms": _elapsed_ms(tls_started),
            "detail": _tls_detail(verify_ssl, metadata),
            "verify_ssl": verify_ssl,
            "tls_version": tls_socket.version(),
            "cipher": cipher_info[0] if cipher_info else None,
            **metadata,
        }
        return tcp_stage, tls_stage, True
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        error = (str(exc).strip() or exc.__class__.__name__)[:240]
        return (
            tcp_stage,
            {
                "id": "tls",
                "label": "TLS handshake",
                "state": "fail",
                "elapsed_ms": _elapsed_ms(tls_started),
                "detail": error,
                "verify_ssl": verify_ssl,
                "failure_stage": "tls_handshake",
            },
            False,
        )
    finally:
        for candidate in (tls_socket, raw_socket):
            if candidate is not None:
                try:
                    candidate.close()
                except OSError:
                    pass


async def collect_tcp_tls_stages(
    host: str,
    port: int,
    verify_ssl: bool,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Run the blocking socket/TLS probe away from the event loop."""
    return await asyncio.to_thread(_tcp_tls_probe, host, port, verify_ssl)
