"""Ordered, non-secret network diagnostics for the TrueNAS platform dependency."""

from __future__ import annotations

import asyncio
import importlib
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
                # Best-effort cleanup must not replace the measured socket result.
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
                # Best-effort cleanup must not replace the measured TLS result.
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


async def _websocket_stage(
    websocket_uri: str,
    verify_ssl: bool,
) -> tuple[dict[str, Any], bool]:
    """Measure a credential-free WebSocket connection with the official TrueNAS client."""
    started = time.perf_counter()

    def connect() -> None:
        module = importlib.import_module("truenas_api_client")
        client = module.Client(uri=websocket_uri, verify_ssl=verify_ssl)
        with client:
            return None

    try:
        await asyncio.wait_for(
            asyncio.to_thread(connect),
            timeout=_DIAGNOSTIC_TIMEOUT_SEC,
        )
    except (Exception, TimeoutError, asyncio.TimeoutError) as exc:
        return (
            _stage(
                "websocket",
                "WebSocket tunnel",
                "fail",
                elapsed_ms=_elapsed_ms(started),
                detail=_error_text(exc),
            ),
            False,
        )

    return (
        _stage(
            "websocket",
            "WebSocket tunnel",
            "ok",
            elapsed_ms=_elapsed_ms(started),
            detail="WebSocket connection established without credentials",
        ),
        True,
    )


def append_truenas_api_stages(
    diagnostics: dict[str, Any],
    api_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Append authentication and API stages without exposing credential material."""
    out = dict(diagnostics)
    stages = [dict(stage) for stage in diagnostics.get("stages", [])]
    websocket = next((stage for stage in stages if stage.get("id") == "websocket"), None)
    websocket_ok = websocket is not None and websocket.get("state") == "ok"

    if not websocket_ok:
        stages.append(
            _stage(
                "authentication",
                "Authentication",
                "blocked",
                detail="Blocked by WebSocket failure",
            )
        )
        stages.append(_stage("api", "TrueNAS API", "blocked", detail="Blocked by authentication"))
        out["stages"] = stages
        return out

    if not isinstance(api_result, dict):
        stages.append(
            _stage(
                "authentication",
                "Authentication",
                "fail",
                detail="TrueNAS API credentials are not configured",
            )
        )
        stages.append(_stage("api", "TrueNAS API", "blocked", detail="Blocked by authentication"))
        out["stages"] = stages
        return out

    reachable = api_result.get("reachable") is True
    phase = str(api_result.get("phase") or "")
    stage = str(api_result.get("stage") or "")
    error = str(api_result.get("error") or "").strip()

    if reachable:
        stages.append(
            _stage(
                "authentication",
                "Authentication",
                "ok",
                elapsed_ms=api_result.get("authentication_elapsed_ms"),
                detail="API key accepted",
            )
        )
        api_detail_parts = []
        if api_result.get("version"):
            api_detail_parts.append(str(api_result["version"]))
        apps = api_result.get("apps")
        if isinstance(apps, list):
            api_detail_parts.append(f"{len(apps)} apps")
        stages.append(
            _stage(
                "api",
                "TrueNAS API",
                "ok",
                elapsed_ms=api_result.get("api_elapsed_ms"),
                detail=" · ".join(api_detail_parts) or "system.version and app.query succeeded",
            )
        )
    elif phase == "authentication" or stage in {
        "missing_api_key",
        "missing_username",
        "invalid_api_key_reference",
        "invalid_api_key_format",
        "authentication",
    }:
        stages.append(
            _stage(
                "authentication",
                "Authentication",
                "fail",
                elapsed_ms=api_result.get("elapsed_ms"),
                detail=error or "TrueNAS authentication failed",
                failure_stage=stage or "authentication",
            )
        )
        stages.append(_stage("api", "TrueNAS API", "blocked", detail="Blocked by authentication"))
    else:
        stages.append(
            _stage(
                "authentication",
                "Authentication",
                "ok",
                detail="Credentials configured; failure occurred after authentication",
            )
        )
        stages.append(
            _stage(
                "api",
                "TrueNAS API",
                "fail",
                elapsed_ms=api_result.get("elapsed_ms"),
                detail=error or "TrueNAS API call failed",
                failure_stage=stage or phase or "api",
            )
        )

    out["stages"] = stages
    return out


async def collect_truenas_network_diagnostics(
    *,
    host: str,
    port: int,
    websocket_uri: str,
    verify_ssl: bool,
    public_result: dict[str, Any],
) -> dict[str, Any]:
    """Measure DNS -> TCP -> TLS -> HTTPS -> WebSocket without credentials."""
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
        tls, tls_ok = await _tls_stage(host, port, verify_ssl)
        stages.append(tls)
    else:
        tls_ok = False
        stages.append(_stage("tls", "TLS handshake", "blocked", detail="Blocked by socket failure"))

    stages.append(_https_stage(public_result))

    if tls_ok:
        websocket, _ = await _websocket_stage(websocket_uri, verify_ssl)
        stages.append(websocket)
    else:
        stages.append(
            _stage(
                "websocket",
                "WebSocket tunnel",
                "blocked",
                detail="Blocked by TLS failure",
            )
        )

    return {
        "target": f"{host}:{port}",
        "websocket_uri": websocket_uri,
        "verify_ssl": verify_ssl,
        "stages": stages,
    }
