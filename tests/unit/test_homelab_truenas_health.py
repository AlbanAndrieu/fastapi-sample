"""TrueNAS transport-path tests for homelab health probing."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from nabla.api import homelab_health, homelab_truenas_probe

@pytest.mark.asyncio
async def test_truenas_transport_diagnostics_timeout_keeps_api_health(monkeypatch) -> None:
    async def api_ok():
        return {
            "reachable": True,
            "version": "TrueNAS-26.0.0-BETA.2",
            "apps": [{"id": "sample"}],
        }

    async def http_ok(*_args, **_kwargs):
        return {
            "name": "TrueNAS HTTPS",
            "url": "https://truenas.albandrieu.com:7000/",
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 1,
        }

    async def slow_diagnostics(**_kwargs):
        await asyncio.sleep(1)
        return {"stages": []}

    monkeypatch.setattr(homelab_truenas_probe, "observe_truenas_health_api", api_ok)
    monkeypatch.setattr(homelab_health, "_probe_http_endpoint", http_ok)
    monkeypatch.setattr(
        homelab_truenas_probe,
        "collect_truenas_network_diagnostics",
        slow_diagnostics,
    )
    monkeypatch.setattr(homelab_truenas_probe, "DIAGNOSTICS_BUDGET_SEC", 0.01)
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(homelab_truenas_probe, "truenas_http_verify_ssl", lambda: True)
    monkeypatch.setattr(homelab_truenas_probe, "homelab_runtime_detected", lambda: True)

    result = await homelab_health._probe_truenas(
        asyncio.Semaphore(2),
        internal_enabled=False,
    )

    assert result["state"] == "ok"
    assert result["public"]["name"] == "TrueNAS HTTPS"
    assert result["api"]["reachable"] is True
    assert result["diagnostics"]["timed_out"] is True
    assert result["diagnostics"]["error_kind"] == "deadline"
    assert result["diagnostics"]["stages"][-2]["id"] == "authentication"
    assert result["diagnostics"]["stages"][-2]["state"] == "ok"
    assert result["diagnostics"]["stages"][-1]["id"] == "api"
    assert result["diagnostics"]["stages"][-1]["state"] == "ok"


@pytest.mark.asyncio
async def test_cloud_runtime_uses_wan_ip_for_raw_tls(monkeypatch) -> None:
    captured = {}

    async def diagnostics(**kwargs):
        captured.update(kwargs)
        return {"stages": []}

    monkeypatch.setattr(
        homelab_truenas_probe,
        "observe_truenas_health_api",
        AsyncMock(return_value={"reachable": True}),
    )
    monkeypatch.setattr(
        homelab_health,
        "_probe_http_endpoint",
        AsyncMock(
            return_value={
                "state": "ok",
                "reachable": True,
                "http_status": 200,
            },
        ),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "collect_truenas_network_diagnostics",
        diagnostics,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_http_verify_ssl",
        lambda: True,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "homelab_runtime_detected",
        lambda: False,
    )

    result = await homelab_health._probe_truenas(
        asyncio.Semaphore(2),
        internal_enabled=False,
    )

    assert captured["host"] == "truenas.albandrieu.com"
    assert captured["connect_host"] == "82.66.4.247"
    assert captured["port"] == 7000
    assert captured["path_mode"] == "public_wan_haproxy"
    assert result["connect_host"] == "82.66.4.247"


@pytest.mark.asyncio
async def test_homelab_runtime_uses_lan_ip_for_raw_tls(monkeypatch) -> None:
    captured = {}

    async def diagnostics(**kwargs):
        captured.update(kwargs)
        return {"stages": []}

    monkeypatch.setattr(
        homelab_truenas_probe,
        "observe_truenas_health_api",
        AsyncMock(return_value={"reachable": True}),
    )
    monkeypatch.setattr(
        homelab_health,
        "_probe_http_endpoint",
        AsyncMock(
            return_value={
                "state": "ok",
                "reachable": True,
                "http_status": 200,
            },
        ),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "collect_truenas_network_diagnostics",
        diagnostics,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_http_verify_ssl",
        lambda: True,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "homelab_runtime_detected",
        lambda: True,
    )
    monkeypatch.setattr(
        homelab_truenas_probe.truenas_probe_health,
        "truenas_internal_target",
        lambda: ("172.17.0.24", 7000),
    )

    result = await homelab_health._probe_truenas(
        asyncio.Semaphore(2),
        internal_enabled=False,
    )

    assert captured["host"] == "truenas.albandrieu.com"
    assert captured["connect_host"] == "172.17.0.24"
    assert captured["port"] == 7000
    assert captured["path_mode"] == "direct_lan"
    assert result["connect_host"] == "172.17.0.24"


@pytest.mark.asyncio
async def test_truenas_payload_separates_appliance_and_public_ingress(monkeypatch) -> None:
    monkeypatch.setattr(
        homelab_truenas_probe,
        "observe_truenas_health_api",
        AsyncMock(return_value={"reachable": True, "version": "TrueNAS-26"}),
    )
    monkeypatch.setattr(
        homelab_health,
        "_probe_http_endpoint",
        AsyncMock(
            return_value={
                "state": "fail",
                "reachable": False,
                "error_kind": "connect_timeout",
                "error": "connect timed out",
            },
        ),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "collect_truenas_network_diagnostics",
        AsyncMock(
            return_value={
                "stages": [
                    {"id": "socket", "state": "ok"},
                    {
                        "id": "tls",
                        "state": "fail",
                        "failure_stage": "tls_handshake",
                        "detail": "handshake timed out",
                    },
                ],
            },
        ),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(homelab_truenas_probe, "truenas_http_verify_ssl", lambda: True)
    monkeypatch.setattr(homelab_truenas_probe, "homelab_runtime_detected", lambda: False)

    result = await homelab_health._probe_truenas(
        asyncio.Semaphore(2),
        internal_enabled=False,
    )

    assert result["appliance_state"] == "ok"
    assert result["public_ingress_state"] == "fail"
    assert result["api"]["reachable"] is True


@pytest.mark.asyncio
async def test_truenas_http_and_transport_probes_start_in_parallel(monkeypatch) -> None:
    http_started = asyncio.Event()
    diagnostics_started = asyncio.Event()
    release = asyncio.Event()

    async def api_ok():
        return {"reachable": True, "version": "TrueNAS-26", "apps": []}

    async def public_https(*_args, **_kwargs):
        http_started.set()
        await release.wait()
        return {
            "name": "TrueNAS public ingress HTTPS",
            "url": "https://truenas.albandrieu.com:7000/",
            "reachable": True,
            "http_status": 200,
            "state": "ok",
            "tls_trusted": True,
            "latency_ms": 10,
        }

    async def transport(**_kwargs):
        diagnostics_started.set()
        await release.wait()
        return {
            "path_mode": "public_wan_haproxy",
            "wan_tls_reachable": True,
            "stages": [
                {"id": "socket", "label": "TCP", "state": "ok"},
                {"id": "tls", "label": "TLS", "state": "ok"},
                {"id": "wan_socket", "label": "WAN TCP", "state": "ok"},
                {"id": "wan_tls", "label": "WAN TLS", "state": "ok"},
                {"id": "websocket", "label": "WebSocket", "state": "ok"},
            ],
        }

    monkeypatch.setattr(homelab_truenas_probe, "observe_truenas_health_api", api_ok)
    monkeypatch.setattr(
        homelab_truenas_probe,
        "probe_truenas_public_https",
        public_https,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "collect_truenas_network_diagnostics",
        transport,
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_url",
        lambda: "https://truenas.albandrieu.com:7000",
    )
    monkeypatch.setattr(
        homelab_truenas_probe,
        "truenas_host_port",
        lambda: ("truenas.albandrieu.com", 7000),
    )
    monkeypatch.setattr(homelab_truenas_probe, "truenas_http_verify_ssl", lambda: True)
    monkeypatch.setattr(homelab_truenas_probe, "homelab_runtime_detected", lambda: False)

    task = asyncio.create_task(
        homelab_health._probe_truenas(
            asyncio.Semaphore(2),
            internal_enabled=False,
        ),
    )
    await asyncio.wait_for(
        asyncio.gather(http_started.wait(), diagnostics_started.wait()),
        timeout=1.0,
    )
    release.set()
    result = await task

    assert result["state"] == "ok"
    assert result["appliance_state"] == "ok"
    assert result["public_ingress_state"] == "ok"
    assert result["diagnostics"]["wan_tls_reachable"] is True
