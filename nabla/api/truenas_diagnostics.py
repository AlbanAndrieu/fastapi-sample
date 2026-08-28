"""Ordered, non-secret network diagnostics for the TrueNAS platform dependency."""

from __future__ import annotations

import asyncio
import socket
import ssl
import time
from typing import Any

_DIAGNOSTIC_TIMEOUT_SEC = 5.0


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _error_text(exc: BaseException) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:240]


def _stage(
    stage_id: str,
    label: str,
    state: str,
    *,
    elapsed_ms: int | None = None,
    detail: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": stage_id, "label": label, "state": state}
    if elapsed_ms is not None:
        row["elapsed_ms"] = elapsed_ms
    if detail:
        row["detail"] = detail
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


async def _dns_stage(host: str) -> tuple[dict[str, Any], bool]:
    started = time.perf_counter()
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM),
            timeout=_DIAGNOSTIC_TIMEOUT_SEC,
        )
    except (OSError, TimeoutError, asyncio.TimeoutError) as exc:
        return (
            _stage(
                "dns",
                "DNS",
                "fail",
                elapsed_ms=_elapsed_ms(started),
                detail=_error_text(exc),
            ),
            False,
        )

    addresses = sorted({str(item[4][0]) for item in results if item and item[4]})
    return (
        _stage(
            "dns",
            "DNS",
            "ok",
            elapsed_ms=_elapsed_ms(started),
            detail=f"{len(addresses)} address(es) resolved",
            resolved=addresses[:4],
        ),
        True,
    )


async def _socket_stage(host: str, port: int) -> tuple[dict[str, Any], bool]:
    started = time.perf_counter()
    writer: asyncio.StreamWriter | None = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=_DIAGNOSTIC_TIMEOUT_SEC
        )
    except (OSError, TimeoutError, asyncio.TimeoutError) as exc:
        return (
            _stage(
                "socket",
                "TCP socket",
                "fail",
                elapsed_ms=_elapsed_ms(started),
                detail=_error_text(exc),
            ),
            False,
        )
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    return (
        _stage(
            "socket",
            "TCP socket",
            "ok",
            elapsed_ms=_elapsed_ms(started),
            detail=f"Connected to {host}:{port}",
        ),
        True,
    )


async def _tls_stage(host: str, port: int, verify_ssl: bool) -> tuple[dict[str, Any], bool]:
    started = time.perf_counter()
    writer: asyncio.StreamWriter | None = None
    context = ssl.create_default_context()
    if not verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host,
                port,
                ssl=context,
                server_hostname=host,
            ),
            timeout=_DIAGNOSTIC_TIMEOUT_SEC,
        )
        ssl_object = writer.get_extra_info("ssl_object")
        tls_version = ssl_object.version() if ssl_object is not None else None
        cipher = ssl_object.cipher()[0] if ssl_object is not None and ssl_object.cipher() else None
    except (OSError, ssl.SSLError, TimeoutError, asyncio.TimeoutError) as exc:
        return (
            _stage(
                "tls",
                "TLS handshake",
                "fail",
                elapsed_ms=_elapsed_ms(started),
                detail=_error_text(exc),
                verify_ssl=verify_ssl,
            ),
            False,
        )
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    return (
        _stage(
            "tls",
            "TLS handshake",
            "ok",
            elapsed_ms=_elapsed_ms(started),
            detail="Certificate trusted" if verify_ssl else "TLS connected without certificate verification",
            verify_ssl=verify_ssl,
            tls_version=tls_version,
            cipher=cipher,
        ),
        True,
    )


def _https_stage(public_result: dict[str, Any]) -> dict[str, Any]:
    reachable = public_result.get("reachable") is True
    state = "ok" if reachable and public_result.get("state") == "ok" else "fail"
    if reachable:
        detail = f"HTTP {public_result.get('http_status', '?')}"
    else:
        detail = str(public_result.get("error") or "HTTPS request failed")[:240]
    return _stage(
        "https",
        "HTTPS",
        state,
        elapsed_ms=public_result.get("latency_ms"),
        detail=detail,
        http_status=public_result.get("http_status"),
        tls_trusted=public_result.get("tls_trusted"),
    )


async def collect_truenas_network_diagnostics(
    *,
    host: str,
    port: int,
    verify_ssl: bool,
    public_result: dict[str, Any],
) -> dict[str, Any]:
    """Measure the ordered DNS -> TCP -> TLS -> HTTPS path without credentials."""
    stages: list[dict[str, Any]] = []
    dns, dns_ok = await _dns_stage(host)
    stages.append(dns)

    if dns_ok:
        socket_stage, socket_ok = await _socket_stage(host, port)
        stages.append(socket_stage)
    else:
        socket_ok = False
        stages.append(_stage("socket", "TCP socket", "blocked", detail="Blocked by DNS failure"))

    if socket_ok:
        tls, _ = await _tls_stage(host, port, verify_ssl)
        stages.append(tls)
    else:
        stages.append(_stage("tls", "TLS handshake", "blocked", detail="Blocked by socket failure"))

    stages.append(_https_stage(public_result))
    return {
        "target": f"{host}:{port}",
        "verify_ssl": verify_ssl,
        "stages": stages,
    }
