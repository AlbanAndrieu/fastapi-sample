"""Tests for the ordered TrueNAS diagnostic pipeline."""

import asyncio

import pytest

from nabla.api.truenas_diagnostics import (
    _direct_lan_stage,
    _haproxy_stage,
    _https_stage,
    _public_path_comparison_stage,
    append_truenas_api_stages,
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


def test_websocket_failure_blocks_authentication() -> None:
    network = _network_ok()
    network["stages"][-1]["state"] = "fail"
    result = append_truenas_api_stages(network, {"reachable": False})

    assert result["stages"][-2]["state"] == "blocked"
    assert result["stages"][-1]["state"] == "blocked"


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


def test_authenticated_api_success_downgrades_auxiliary_websocket_failure() -> None:
    network = _network_ok()
    network["stages"][-1]["state"] = "fail"
    network["stages"][-1]["detail"] = "timed out"

    result = append_truenas_api_stages(
        network,
        {"reachable": True, "version": "TrueNAS-26", "apps": []},
    )

    websocket = next(stage for stage in result["stages"] if stage["id"] == "websocket")
    assert websocket["state"] == "warn"
    assert websocket["contradicted_by"] == "authenticated_api_success"



def test_authenticated_api_success_downgrades_auxiliary_tcp_tls_failures() -> None:
    network = _network_ok()
    network["stages"][1].update({"state": "fail", "detail": "connect timed out"})
    network["stages"][2].update({"state": "fail", "detail": "TLS timed out"})

    result = append_truenas_api_stages(
        network,
        {"reachable": True, "version": "TrueNAS-26", "apps": []},
    )

    socket = next(stage for stage in result["stages"] if stage["id"] == "socket")
    tls = next(stage for stage in result["stages"] if stage["id"] == "tls")
    assert socket["state"] == "warn"
    assert tls["state"] == "warn"
    assert socket["contradicted_by"] == "authenticated_api_success"
    assert tls["contradicted_by"] == "authenticated_api_success"



@pytest.mark.asyncio
async def test_transport_and_websocket_diagnostics_start_concurrently(monkeypatch) -> None:
    from nabla.api import truenas_diagnostics as diagnostics

    started: set[str] = set()
    all_started = asyncio.Event()
    release = asyncio.Event()

    def mark_started(label: str) -> None:
        started.add(label)
        if len(started) == 4:
            all_started.set()

    async def dns(_host: str):
        mark_started("dns")
        await release.wait()
        return (
            {
                "id": "dns",
                "label": "DNS",
                "state": "ok",
                "resolved": ["82.66.4.247"],
            },
            True,
        )

    async def transport(*_args, connect_host=None, **_kwargs):
        mark_started("wan" if connect_host else "hostname")
        await release.wait()
        return (
            {"id": "socket", "label": "TCP", "state": "ok"},
            {"id": "tls", "label": "TLS", "state": "ok"},
            True,
        )

    async def websocket(*_args, **_kwargs):
        mark_started("websocket")
        await release.wait()
        return (
            {"id": "websocket", "label": "WebSocket", "state": "ok"},
            True,
        )

    monkeypatch.setattr(diagnostics, "_dns_stage", dns)
    monkeypatch.setattr(diagnostics, "collect_tcp_tls_stages", transport)
    monkeypatch.setattr(diagnostics, "_websocket_stage", websocket)
    monkeypatch.setattr(
        diagnostics,
        "homelab_wan_metadata",
        lambda: {"ipv4": "82.66.4.247", "provider": "Free", "static": True},
    )

    task = asyncio.create_task(
        diagnostics.collect_truenas_network_diagnostics(
            host="truenas.albandrieu.com",
            port=7000,
            websocket_uri="wss://truenas.albandrieu.com:7000/api/current",
            verify_ssl=True,
            public_result={"reachable": True, "state": "ok", "http_status": 200},
        ),
    )
    await asyncio.wait_for(all_started.wait(), timeout=1.0)
    assert started == {"dns", "hostname", "wan", "websocket"}
    release.set()
    result = await task

    assert result["wan_tls_reachable"] is True
    assert any(stage["id"] == "websocket" for stage in result["stages"])


@pytest.mark.asyncio
async def test_websocket_success_downgrades_contradictory_tls_failure(monkeypatch) -> None:
    from nabla.api import truenas_diagnostics as diagnostics

    async def dns(_host: str):
        return (
            {
                "id": "dns",
                "label": "DNS",
                "state": "ok",
                "resolved": ["82.66.4.247"],
            },
            True,
        )

    async def transport(*_args, connect_host=None, **_kwargs):
        if connect_host:
            return (
                {"id": "socket", "label": "TCP", "state": "ok"},
                {"id": "tls", "label": "TLS", "state": "ok"},
                True,
            )
        return (
            {"id": "socket", "label": "TCP", "state": "ok"},
            {
                "id": "tls",
                "label": "TLS",
                "state": "fail",
                "detail": "handshake timed out",
            },
            False,
        )

    async def websocket(*_args, **_kwargs):
        return (
            {"id": "websocket", "label": "WebSocket", "state": "ok"},
            True,
        )

    monkeypatch.setattr(diagnostics, "_dns_stage", dns)
    monkeypatch.setattr(diagnostics, "collect_tcp_tls_stages", transport)
    monkeypatch.setattr(diagnostics, "_websocket_stage", websocket)
    monkeypatch.setattr(
        diagnostics,
        "homelab_wan_metadata",
        lambda: {"ipv4": "82.66.4.247", "provider": "Free", "static": True},
    )

    result = await diagnostics.collect_truenas_network_diagnostics(
        host="truenas.albandrieu.com",
        port=7000,
        websocket_uri="wss://truenas.albandrieu.com:7000/api/current",
        verify_ssl=True,
        public_result={"reachable": False, "state": "fail"},
    )

    tls = next(stage for stage in result["stages"] if stage["id"] == "tls")
    assert tls["state"] == "warn"
    assert tls["contradicted_by"] == "websocket_success"
