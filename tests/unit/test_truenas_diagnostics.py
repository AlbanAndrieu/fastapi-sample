"""Tests for the ordered TrueNAS diagnostic pipeline."""

from nabla.api.truenas_diagnostics import (
    _direct_lan_stage,
    _haproxy_stage,
    _https_stage,
    _public_path_comparison_stage,
    append_truenas_api_stages,
    unmeasured_truenas_network_diagnostics,
)


def _network_ok():
    return {
        "target": "truenas.example:7000",
        "stages": [
            {"id": "dns", "label": "DNS", "state": "ok"},
            {"id": "socket", "label": "TCP connect", "state": "ok"},
            {"id": "tls", "label": "TLS handshake", "state": "ok"},
            {"id": "https", "label": "HTTPS", "state": "ok"},
            {
                "id": "haproxy",
                "label": "HAProxy WebSocket proxy",
                "state": "ok",
            },
            {"id": "websocket", "label": "WebSocket upgrade", "state": "ok"},
        ],
    }


def test_direct_lan_stage_documents_public_path_bypass() -> None:
    stage = _direct_lan_stage(True, "truenas.albandrieu.com", 7000)

    assert stage["id"] == "direct_lan"
    assert stage["state"] == "ok"
    assert "public pfSense WAN and HAProxy path bypassed" in stage["detail"]


def test_haproxy_stage_documents_websocket_and_tls_reencryption() -> None:
    stage = _haproxy_stage(True)

    assert stage["id"] == "haproxy"
    assert stage["state"] == "ok"
    assert stage["proxy_mode"] == "http"
    assert stage["websocket_upgrade"] == "native"
    assert stage["backend_tls"] == "re-encryption"


def test_missing_api_key_marks_auth_failed_and_api_blocked() -> None:
    result = append_truenas_api_stages(
        _network_ok(),
        {
            "reachable": False,
            "phase": "authentication",
            "stage": "missing_api_key",
            "error": "TRUENAS_API_KEY is missing; authentication cannot be attempted.",
        },
    )

    auth, api = result["stages"][-2:]
    assert auth["id"] == "authentication"
    assert auth["state"] == "fail"
    assert auth["failure_stage"] == "missing_api_key"
    assert api == {
        "id": "api",
        "label": "TrueNAS API · system.version + app.query",
        "state": "blocked",
        "detail": "Blocked by authentication",
    }


def test_api_failure_preserves_explicit_auxiliary_websocket_evidence() -> None:
    network = _network_ok()
    network["stages"][-1]["state"] = "fail"
    result = append_truenas_api_stages(
        network,
        {
            "reachable": False,
            "phase": "connect",
            "stage": "connection_reset",
            "error": "Connection reset by peer",
        },
    )

    websocket = next(stage for stage in result["stages"] if stage["id"] == "websocket")
    assert websocket["state"] == "fail"
    assert result["stages"][-2]["state"] == "ok"
    assert result["stages"][-1]["state"] == "fail"


def test_authenticated_api_supplies_websocket_evidence_without_extra_probe() -> None:
    network = _network_ok()
    network["stages"] = [
        stage for stage in network["stages"] if stage["id"] != "websocket"
    ]

    result = append_truenas_api_stages(
        network,
        {
            "reachable": True,
            "version": "TrueNAS-26.0.0",
            "apps": [],
        },
    )

    websocket = next(stage for stage in result["stages"] if stage["id"] == "websocket")
    assert websocket["state"] == "ok"
    assert websocket["evidence"] == "authenticated_api_probe"


def test_authenticated_api_success_overrides_auxiliary_websocket_failure() -> None:
    network = _network_ok()
    network["stages"][-1]["state"] = "fail"
    result = append_truenas_api_stages(
        network,
        {
            "reachable": True,
            "version": "TrueNAS-26.0.0-BETA.2",
            "apps": [{"id": "sample"}],
        },
    )

    auth, api = result["stages"][-2:]
    assert auth["id"] == "authentication"
    assert auth["state"] == "ok"
    assert api["id"] == "api"
    assert api["state"] == "ok"
    assert "1 apps" in api["detail"]


def test_https_stage_preserves_probe_warning_for_deadline() -> None:
    stage = _https_stage(
        {
            "reachable": False,
            "state": "warn",
            "timed_out": True,
            "error_kind": "deadline",
            "error": "service probe fan-out budget exceeded",
            "http_status": 0,
            "tls_trusted": None,
        },
        path_mode="public_wan_haproxy",
    )

    assert stage["state"] == "warn"
    assert "budget exceeded" in stage["detail"]


def test_https_stage_keeps_redirect_operational() -> None:
    stage = _https_stage(
        {
            "reachable": True,
            "state": "ok",
            "http_status": 302,
            "tls_trusted": True,
        },
        path_mode="public_wan_haproxy",
    )

    assert stage["state"] == "ok"
    assert stage["http_status"] == 302
    assert stage["detail"] == "HTTP 302"


def test_https_stage_keeps_transport_failure_failed() -> None:
    stage = _https_stage(
        {
            "reachable": False,
            "state": "fail",
            "error": "Connection refused",
            "http_status": 0,
            "tls_trusted": None,
        },
        path_mode="public_wan_haproxy",
    )

    assert stage["state"] == "fail"
    assert stage["detail"] == "Connection refused"


def test_authenticated_api_downgrades_auxiliary_raw_tls_failure() -> None:
    network = _network_ok()
    network["stages"][2] = {
        "id": "tls",
        "label": "TLS handshake",
        "state": "fail",
        "detail": "handshake timed out",
    }

    result = append_truenas_api_stages(
        network,
        {
            "reachable": True,
            "version": "TrueNAS-26.0.0",
            "apps": [],
        },
    )

    tls = next(stage for stage in result["stages"] if stage["id"] == "tls")
    assert tls["state"] == "warn"
    assert tls["superseded_by"] == "authenticated_api"
    assert "raw-socket and application egress paths may differ" in tls["detail"]


def test_authenticated_api_downgrades_blocked_route_stages() -> None:
    network = _network_ok()
    for stage in network["stages"][:-1]:
        if stage["id"] in {"socket", "tls", "haproxy", "https"}:
            stage["state"] = "blocked"
            stage["detail"] = "auxiliary path blocked"

    result = append_truenas_api_stages(
        network,
        {
            "reachable": True,
            "version": "TrueNAS-26.0.0",
            "apps": [],
        },
    )

    reconciled = {stage["id"]: stage for stage in result["stages"] if stage["id"] in {"socket", "tls", "haproxy", "https"}}
    assert all(stage["state"] == "warn" for stage in reconciled.values())
    assert all(stage["evidence_conflict"] is True for stage in reconciled.values())


def test_wan_path_comparison_identifies_hostname_edge_mismatch() -> None:
    stage = _public_path_comparison_stage(
        resolved=["104.16.1.1"],
        wan_ipv4="82.66.4.247",
        hostname_tls_ok=False,
        wan_tls_ok=True,
    )

    assert stage["state"] == "warn"
    assert stage["dns_matches_wan"] is False
    assert "DNS/proxy/edge" in stage["detail"]


def test_unmeasured_diagnostics_use_declared_host_as_connect_target() -> None:
    result = unmeasured_truenas_network_diagnostics(
        host="truenas.albandrieu.com",
        port=7000,
        websocket_uri="wss://truenas.albandrieu.com:7000/api/current",
        verify_ssl=True,
        path_mode="public_wan_haproxy",
        budget_seconds=3.0,
    )

    assert result["connect_target"] == "truenas.albandrieu.com:7000"
    assert result["timed_out"] is True
    assert result["error_kind"] == "deadline"
