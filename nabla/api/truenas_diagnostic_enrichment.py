"""Compose HTTP and authenticated API evidence into TrueNAS diagnostics."""

from __future__ import annotations

from typing import Any


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


def _https_stage(
    public_result: dict[str, Any],
    *,
    path_mode: str,
) -> dict[str, Any]:
    reachable = public_result.get("reachable") is True
    public_state = str(public_result.get("state") or "").strip().lower()
    timed_out = public_result.get("timed_out") is True
    error_kind = str(public_result.get("error_kind") or "").strip().lower()

    if timed_out or error_kind == "deadline" or public_state == "warn":
        state = "warn"
    elif reachable and public_state == "ok":
        state = "ok"
    else:
        state = "fail"

    if reachable:
        detail = f"HTTP {public_result.get('http_status', '?')}"
    elif state == "warn":
        detail = str(
            public_result.get("error")
            or "HTTPS probe inconclusive; endpoint availability was not disproved",
        )[:240]
    else:
        detail = str(public_result.get("error") or "HTTPS request failed")[:240]
    return _stage(
        "https",
        (
            "TrueNAS HTTPS listener"
            if path_mode == "direct_lan"
            else "HTTPS listener via HAProxy"
        ),
        state,
        elapsed_ms=public_result.get("latency_ms"),
        detail=detail,
        http_status=public_result.get("http_status"),
        tls_trusted=public_result.get("tls_trusted"),
    )


def _retag_wan_transport_stage(
    stage: dict[str, Any],
    *,
    stage_id: str,
    label: str,
) -> dict[str, Any]:
    return {
        **stage,
        "id": stage_id,
        "label": label,
        "evidence": "direct_wan_probe",
    }


def _public_path_comparison_stage(
    *,
    resolved: list[str],
    wan_ipv4: str,
    hostname_tls_ok: bool,
    wan_tls_ok: bool,
) -> dict[str, Any]:
    dns_matches_wan = wan_ipv4 in resolved
    if hostname_tls_ok and wan_tls_ok and dns_matches_wan:
        state = "ok"
        detail = (
            "Hostname and direct WAN+SNI TLS both succeed; "
            f"DNS includes {wan_ipv4}."
        )
    elif wan_tls_ok and not hostname_tls_ok:
        state = "warn"
        detail = (
            "Direct WAN+SNI TLS succeeds while the hostname TLS probe fails. "
            "Investigate DNS/proxy/edge routing before pfSense or TrueNAS."
        )
    elif hostname_tls_ok and not wan_tls_ok:
        state = "warn"
        detail = (
            "Hostname TLS succeeds while the configured WAN IP TLS probe fails. "
            "The hostname is reaching another path; direct pfSense/HAProxy "
            "ingress is not confirmed."
        )
    elif not dns_matches_wan:
        state = "warn"
        detail = (
            f"DNS resolves to {', '.join(resolved) or 'no address'}, not "
            f"configured WAN IPv4 {wan_ipv4}; the hostname path is not the "
            "declared direct pfSense/HAProxy route."
        )
    else:
        state = "fail"
        detail = (
            "Neither hostname TLS nor direct WAN+SNI TLS completed. Inspect "
            "pfSense WAN policy, Snort/pfBlockerNG and HAProxy :7000."
        )
    return _stage(
        "wan_path_comparison",
        "Hostname ↔ WAN :7000",
        state,
        detail=detail,
        configured_wan_ipv4=wan_ipv4,
        dns_matches_wan=dns_matches_wan,
        hostname_tls_ok=hostname_tls_ok,
        wan_tls_ok=wan_tls_ok,
    )


def _haproxy_stage(tls_ok: bool) -> dict[str, Any]:
    """Describe the declared HAProxy hop without claiming a config API probe."""
    if not tls_ok:
        return _stage(
            "haproxy",
            "HAProxy :7000",
            "blocked",
            detail="Blocked before the public HAProxy TLS listener could be validated",
        )
    return _stage(
        "haproxy",
        "HAProxy :7000",
        "ok",
        detail=(
            "Public TLS termination · HTTP mode · native WebSocket upgrade "
            "forwarding · TLS re-encryption to TrueNAS 172.17.0.24:7000"
        ),
        evidence="declared_topology",
        proxy_mode="http",
        websocket_upgrade="native",
        backend_tls="re-encryption",
    )


def append_truenas_http_stage(
    diagnostics: dict[str, Any],
    public_result: dict[str, Any],
) -> dict[str, Any]:
    """Merge bounded HTTP evidence into transport diagnostics without re-probing."""
    out = dict(diagnostics)
    path_mode = str(out.get("path_mode") or "public_wan_haproxy")
    https_stage = _https_stage(public_result, path_mode=path_mode)
    stages = [
        dict(stage)
        for stage in out.get("stages", [])
        if isinstance(stage, dict) and stage.get("id") != "https"
    ]
    insert_at = next(
        (
            index
            for index, stage in enumerate(stages)
            if stage.get("id") in {"websocket", "authentication", "api"}
        ),
        len(stages),
    )
    stages.insert(insert_at, https_stage)
    out["stages"] = stages
    return out


def _failed_api_stage(
    api_result: dict[str, Any],
    *,
    phase: str,
    stage: str,
    method: str,
    error: str,
) -> dict[str, Any]:
    rpc_method = (
        method
        if method and method not in {"connect", "auth.login_with_api_key"}
        else ""
    )
    api_label = (
        f"TrueNAS API · {rpc_method}"
        if rpc_method
        else "TrueNAS API · system.version + app.query"
    )
    api_detail = error or "TrueNAS API call failed"
    if rpc_method:
        api_detail = f"{rpc_method}: {api_detail}"
    return _stage(
        "api",
        api_label,
        "fail",
        elapsed_ms=api_result.get("elapsed_ms"),
        detail=api_detail,
        failure_stage=stage or phase or "api",
        rpc_method=rpc_method or None,
    )


def append_truenas_api_stages(
    diagnostics: dict[str, Any],
    api_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Append authentication and API stages without exposing credential material."""
    out = dict(diagnostics)
    stages = [dict(stage) for stage in diagnostics.get("stages", [])]
    path_mode = str(out.get("path_mode") or "public_wan_haproxy")
    websocket = next(
        (stage for stage in stages if stage.get("id") == "websocket"),
        None,
    )
    websocket_label = (
        "TrueNAS WebSocket /api/current · direct LAN"
        if path_mode == "direct_lan"
        else "TrueNAS WebSocket /api/current · WAN/HAProxy"
    )
    if websocket is not None:
        websocket["label"] = websocket_label
    if not isinstance(api_result, dict):
        stages.append(
            _stage(
                "authentication",
                "TrueNAS API authentication",
                "fail",
                detail="TrueNAS API credentials are not configured",
            ),
        )
        stages.append(
            _stage(
                "api",
                "TrueNAS API · system.version + app.query",
                "blocked",
                detail="Blocked by authentication",
            ),
        )
        out["stages"] = stages
        return out

    reachable = api_result.get("reachable") is True
    phase = str(api_result.get("phase") or "")
    stage = str(api_result.get("stage") or "")
    method = str(api_result.get("method") or "").strip()
    error = str(api_result.get("error") or "").strip()
    authenticated = api_result.get("authenticated") is True
    websocket_established = (
        reachable or authenticated or phase in {"authentication", "call"}
    )

    if websocket is not None and websocket_established:
        websocket.update(
            {
                "state": "ok",
                "detail": (
                    "WebSocket /api/current established; "
                    "probe advanced to authentication/RPC"
                ),
                "evidence": "authenticated_api_probe",
                "confirmation": "established",
            },
        )
        websocket.pop("failure_stage", None)

    if websocket is None:
        websocket_state = "ok" if websocket_established else "fail"
        if websocket_established:
            websocket_detail = (
                "WebSocket /api/current established; "
                "probe advanced to authentication/RPC"
            )
        else:
            websocket_detail = error or "WebSocket /api/current connection failed"
            if path_mode != "direct_lan":
                websocket_detail = (
                    f"{websocket_detail} · public WAN/HAProxy path; "
                    "TrueNAS appliance liveness is evaluated separately"
                )
        stages.append(
            _stage(
                "websocket",
                websocket_label,
                websocket_state,
                elapsed_ms=(
                    api_result.get("websocket_elapsed_ms")
                    if websocket_established
                    else api_result.get("elapsed_ms")
                ),
                detail=websocket_detail,
                evidence="authenticated_api_probe",
                failure_stage=(
                    None
                    if websocket_established
                    else stage or phase or "websocket"
                ),
                confirmation="established" if websocket_established else "failed",
            ),
        )

    if reachable:
        for auxiliary in stages:
            if auxiliary.get("id") not in {
                "socket",
                "tls",
                "haproxy",
                "direct_lan",
                "https",
                "websocket",
            } or auxiliary.get("state") not in {"fail", "blocked"}:
                continue
            original = str(
                auxiliary.get("detail") or "auxiliary transport probe failed",
            )
            auxiliary["state"] = "warn"
            auxiliary["detail"] = (
                f"{original} · authenticated TrueNAS API succeeded; "
                "raw-socket and application egress paths may differ"
            )
            auxiliary["contradicted_by"] = "authenticated_api_success"
            auxiliary["superseded_by"] = "authenticated_api"
            auxiliary["evidence_conflict"] = True
        stages.append(
            _stage(
                "authentication",
                "TrueNAS API authentication",
                "ok",
                elapsed_ms=api_result.get("authentication_elapsed_ms"),
                detail="API key accepted",
            ),
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
                "TrueNAS API · system.version + app.query",
                "ok",
                elapsed_ms=api_result.get("api_elapsed_ms"),
                detail=(
                    " · ".join(api_detail_parts)
                    or "system.version and app.query succeeded"
                ),
            ),
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
                "TrueNAS API authentication",
                "fail",
                elapsed_ms=api_result.get("elapsed_ms"),
                detail=error or "TrueNAS authentication failed",
                failure_stage=stage or "authentication",
            ),
        )
        stages.append(
            _stage(
                "api",
                "TrueNAS API · system.version + app.query",
                "blocked",
                detail="Blocked by authentication",
            ),
        )
    else:
        auth_accepted = (
            api_result.get("authenticated") is True
            or api_result.get("authentication_succeeded") is True
        )
        if auth_accepted:
            authentication_state = "ok"
            authentication_detail = (
                "API key accepted; failure occurred after authentication"
            )
        else:
            authentication_state = "warn"
            authentication_detail = (
                "TrueNAS API credentials are configured, but the WebSocket/API "
                "transport failed before TrueNAS could evaluate authentication"
            )
        stages.append(
            _stage(
                "authentication",
                "TrueNAS API authentication",
                authentication_state,
                elapsed_ms=api_result.get("authentication_elapsed_ms"),
                detail=authentication_detail,
                confirmation="accepted" if auth_accepted else "unconfirmed",
            ),
        )
        if auth_accepted:
            stages.append(
                _failed_api_stage(
                    api_result,
                    phase=phase,
                    stage=stage,
                    method=method,
                    error=error,
                ),
            )
        else:
            stages.append(
                _stage(
                    "api",
                    "TrueNAS API · system.version + app.query",
                    "blocked",
                    elapsed_ms=api_result.get("elapsed_ms"),
                    detail=(
                        "Not evaluated: WebSocket/API transport failed before "
                        "TrueNAS authentication"
                    ),
                    failure_stage=stage or phase or "connect",
                ),
            )

    out["stages"] = stages
    return out
