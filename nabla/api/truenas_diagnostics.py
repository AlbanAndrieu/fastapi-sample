"""Ordered, non-secret network diagnostics for the TrueNAS platform dependency."""

from __future__ import annotations

import asyncio
import importlib
import socket
import time
from typing import Any

from nabla.api.truenas_diagnostic_enrichment import (
    _haproxy_stage,
    _public_path_comparison_stage,
    _retag_wan_transport_stage,
)
from nabla.api import truenas_diagnostic_enrichment as _diagnostic_enrichment
from nabla.api.truenas_transport_diagnostics import (
    collect_tcp_tls_stages,
    homelab_wan_metadata,
)

_DIAGNOSTIC_TIMEOUT_SEC = 2.5
_DIAGNOSTIC_CONTRACT = "truenas-public-path-v2"


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


def _direct_lan_stage(tls_ok: bool, host: str, port: int) -> dict[str, Any]:
    """Describe the trusted-LAN route used by the TrueNAS-hosted runtime."""
    if not tls_ok:
        return _stage(
            "direct_lan",
            "Direct LAN route",
            "blocked",
            detail="Blocked before the direct TrueNAS TLS listener could be validated",
        )
    return _stage(
        "direct_lan",
        "Direct LAN route",
        "ok",
        detail=(f"Split DNS/direct LAN to {host}:{port} · public pfSense WAN and HAProxy path bypassed"),
        evidence="runtime_route",
    )


def unmeasured_truenas_network_diagnostics(
    *,
    host: str,
    port: int,
    websocket_uri: str,
    verify_ssl: bool,
    path_mode: str,
    budget_seconds: float,
) -> dict[str, Any]:
    """Return the declared transport path when detailed measurement exceeds its budget."""
    detail = f"Not measured within {budget_seconds:g}s TrueNAS transport diagnostics budget"
    route_id = "direct_lan" if path_mode == "direct_lan" else "haproxy"
    route_label = "Direct LAN route" if path_mode == "direct_lan" else "HAProxy :7000"
    return {
        "target": f"{host}:{port}",
        "connect_target": f"{host}:{port}",
        "server_name": host,
        "path_mode": path_mode,
        "wan": None if path_mode == "direct_lan" else homelab_wan_metadata(),
        "websocket_uri": websocket_uri,
        "verify_ssl": verify_ssl,
        "diagnostic_contract": _DIAGNOSTIC_CONTRACT,
        "transport_timeout_seconds": _DIAGNOSTIC_TIMEOUT_SEC,
        "diagnostics_budget_seconds": budget_seconds,
        "timed_out": True,
        "error_kind": "deadline",
        "stages": [
            _stage("dns", "DNS resolution", "blocked", detail=detail),
            _stage("socket", "TCP :7000", "blocked", detail=detail),
            _stage("tls", "TLS handshake", "blocked", detail=detail),
            *(
                []
                if path_mode == "direct_lan"
                else [
                    _stage("wan_socket", "WAN TCP :7000", "blocked", detail=detail),
                    _stage("wan_tls", "WAN TLS + SNI", "blocked", detail=detail),
                    _stage(
                        "wan_path_comparison",
                        "Hostname ↔ WAN :7000",
                        "blocked",
                        detail=detail,
                    ),
                ]
            ),
            _stage(route_id, route_label, "blocked", detail=detail),
            _stage("https", "TrueNAS HTTPS listener", "blocked", detail=detail),
            _stage("websocket", "WebSocket /api/current", "blocked", detail=detail),
        ],
    }


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
            detail="WebSocket /api/current connection established to TrueNAS without credentials",
        ),
        True,
    )


async def collect_truenas_network_diagnostics(
    *,
    host: str,
    port: int,
    websocket_uri: str,
    connect_host: str | None = None,
    verify_ssl: bool,
    path_mode: str = "public_wan_haproxy",
) -> dict[str, Any]:
    """Measure hostname and direct-WAN transport paths within one bounded window."""
    stages: list[dict[str, Any]] = []
    wan = None if path_mode == "direct_lan" else homelab_wan_metadata()

    socket_target = connect_host or host
    probes: list[Any] = [_dns_stage(host)]
    if path_mode == "direct_lan":
        probes.append(
            collect_tcp_tls_stages(
                host,
                port,
                verify_ssl,
                connect_host=socket_target,
                server_name=host,
            ),
        )
    else:
        probes.append(
            collect_tcp_tls_stages(
                host,
                port,
                verify_ssl,
                server_name=host,
            ),
        )
    probes.append(_websocket_stage(websocket_uri, verify_ssl))
    if wan is not None:
        probes.append(
            collect_tcp_tls_stages(
                host,
                port,
                verify_ssl,
                connect_host=socket_target,
                server_name=host,
            ),
        )

    results = await asyncio.gather(*probes)
    dns, _dns_ok = results[0]
    socket_stage, tls_stage, tls_ok = results[1]
    websocket, websocket_ok = results[2]
    wan_result = results[3] if len(results) > 3 else None
    resolved = [str(value) for value in dns.get("resolved", []) if value]
    stages.append(dns)

    stages.extend((socket_stage, tls_stage))

    wan_tls_ok: bool | None = None
    if wan_result is not None:
        wan_socket, wan_tls, wan_tls_ok = wan_result
        stages.extend(
            (
                _retag_wan_transport_stage(
                    wan_socket,
                    stage_id="wan_socket",
                    label="WAN TCP :7000",
                ),
                _retag_wan_transport_stage(
                    wan_tls,
                    stage_id="wan_tls",
                    label="WAN TLS + SNI",
                ),
            ),
        )
        stages.append(
            _public_path_comparison_stage(
                resolved=resolved,
                wan_ipv4=str(wan["ipv4"]),
                hostname_tls_ok=tls_ok,
                wan_tls_ok=wan_tls_ok,
            ),
        )

    if path_mode == "direct_lan":
        stages.append(_direct_lan_stage(tls_ok, socket_target, port))
    else:
        stages.append(_haproxy_stage(wan_tls_ok is True))

    if websocket_ok and tls_stage.get("state") == "fail":
        tls_stage["state"] = "warn"
        tls_stage["detail"] = (
            f"{tls_stage.get('detail', 'auxiliary TLS probe failed')} · "
            "credential-free WebSocket connected on the same hostname; "
            "the isolated TLS result is contradictory auxiliary evidence."
        )
        tls_stage["contradicted_by"] = "websocket_success"
        tls_stage["superseded_by"] = "websocket_success"
        tls_stage["evidence_conflict"] = True
    stages.append(websocket)

    return {
        "target": f"{host}:{port}",
        "connect_target": f"{socket_target}:{port}",
        "server_name": host,
        "path_mode": path_mode,
        "wan": wan,
        "wan_tls_reachable": wan_tls_ok,
        "websocket_uri": websocket_uri,
        "verify_ssl": verify_ssl,
        "diagnostic_contract": _DIAGNOSTIC_CONTRACT,
        "transport_timeout_seconds": _DIAGNOSTIC_TIMEOUT_SEC,
        "stages": stages,
    }


# Compatibility aliases retained for callers and tests that import these helpers here.
_https_stage = _diagnostic_enrichment._https_stage
append_truenas_api_stages = _diagnostic_enrichment.append_truenas_api_stages
append_truenas_http_stage = _diagnostic_enrichment.append_truenas_http_stage
