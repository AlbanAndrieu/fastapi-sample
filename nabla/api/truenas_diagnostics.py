"""Ordered, non-secret network diagnostics for the TrueNAS platform dependency."""

from __future__ import annotations

import asyncio
import importlib
import socket
import time
from typing import Any

from nabla.api.truenas_transport_diagnostics import (
    collect_tcp_tls_stages,
    homelab_wan_metadata,
)

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


def _haproxy_stage(tls_ok: bool) -> dict[str, Any]:
    """Describe the declared HAProxy hop without claiming a config API probe."""
    if not tls_ok:
        return _stage(
            "haproxy",
            "HAProxy WebSocket proxy",
            "blocked",
            detail="Blocked before the public HAProxy listener could be validated",
        )
    return _stage(
        "haproxy",
        "HAProxy WebSocket proxy",
        "ok",
        detail=(
            "HAProxy :7000 · HTTP mode · native WebSocket upgrade forwarding · "
            "TLS re-encryption to TrueNAS; WebSocket path validated next"
        ),
        evidence="declared_topology",
        proxy_mode="http",
        websocket_upgrade="native",
        backend_tls="re-encryption",
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
                "WebSocket upgrade",
                "fail",
                elapsed_ms=_elapsed_ms(started),
                detail=_error_text(exc),
            ),
            False,
        )

    return (
        _stage(
            "websocket",
            "WebSocket upgrade",
            "ok",
            elapsed_ms=_elapsed_ms(started),
            detail="WebSocket connection established through HAProxy to TrueNAS without credentials",
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
    """Measure DNS -> TCP -> TLS -> HTTPS -> HAProxy -> WebSocket without credentials."""
    stages: list[dict[str, Any]] = []
    dns, dns_ok = await _dns_stage(host)
    stages.append(dns)

    if dns_ok:
        socket_stage, tls_stage, tls_ok = await collect_tcp_tls_stages(host, port, verify_ssl)
        stages.extend((socket_stage, tls_stage))
    else:
        tls_ok = False
        stages.append(_stage("socket", "TCP connect", "blocked", detail="Blocked by DNS failure"))
        stages.append(_stage("tls", "TLS handshake", "blocked", detail="Blocked by DNS failure"))

    stages.append(_https_stage(public_result))
    stages.append(_haproxy_stage(tls_ok))

    if tls_ok:
        websocket, _ = await _websocket_stage(websocket_uri, verify_ssl)
        stages.append(websocket)
    else:
        stages.append(
            _stage(
                "websocket",
                "WebSocket upgrade",
                "blocked",
                detail="Blocked before HAProxy/WebSocket validation",
            )
        )

    return {
        "target": f"{host}:{port}",
        "wan": homelab_wan_metadata(),
        "websocket_uri": websocket_uri,
        "verify_ssl": verify_ssl,
        "stages": stages,
    }
