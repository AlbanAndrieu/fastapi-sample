"""Contract tests for extracted homelab HTTP/TCP probe execution."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "ok"),
        (301, "ok"),
        (401, "warn"),
        (403, "warn"),
        (407, "warn"),
        (429, "warn"),
        (404, "fail"),
        (500, "fail"),
        (530, "fail"),
        (0, "fail"),
    ],
)
def test_classify_public_http_status(status: int, expected: str) -> None:
    assert homelab_health.classify_public_http_status(status) == expected


def test_internal_probes_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("HOMELAB_INTERNAL_PROBES_ENABLED", raising=False)

    assert homelab_health.internal_probes_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_internal_probes_can_be_explicitly_enabled(monkeypatch, value: str) -> None:
    monkeypatch.setenv("HOMELAB_INTERNAL_PROBES_ENABLED", value)

    assert homelab_health.internal_probes_enabled() is True


@pytest.mark.asyncio
async def test_internal_tcp_probe_reports_reachability(monkeypatch) -> None:
    writer = Mock()
    writer.wait_closed = AsyncMock()
    open_connection = AsyncMock(return_value=(Mock(), writer))
    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    service = HomelabService(
        name="Internal service",
        internalHost="192.168.1.30",
        internalPort=8443,
        external=False,
    )

    result = await homelab_health._probe_internal_service(
        asyncio.Semaphore(1),
        service,
    )

    open_connection.assert_awaited_once_with("192.168.1.30", 8443)
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once_with()
    assert result["reachable"] is True
    assert result["state"] == "ok"
    assert result["host"] == "192.168.1.30"
    assert result["port"] == 8443


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "state"),
    [(200, "ok"), (403, "warn"), (404, "fail"), (530, "fail")],
)
async def test_probe_preserves_real_http_status(status: int, state: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["reachable"] is True
    assert result["http_status"] == status
    assert result["state"] == state
    assert result["tls_trusted"] is True


@pytest.mark.asyncio
async def test_cloudflare_access_probe_uses_service_token_for_origin_health(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    edge_probe = AsyncMock(
        return_value={
            "cloudflare_http_evidence": True,
            "cloudflare_access_signal": False,
            "cloudflare_default_deny": True,
            "http_evidence_status": 403,
            "http_probe_auth_mode": "anonymous",
            "cloudflare_service_auth_attempted": True,
            "cloudflare_service_token_access_passed": True,
            "cloudflare_service_token_http_status": 200,
        },
    )
    monkeypatch.setattr(homelab_health, "_probe_http_edge_evidence", edge_probe)
    service = HomelabService(
        id="garage-webui",
        name="Garage",
        tunnelUrl="https://garage.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    edge_probe.assert_awaited_once_with("https://garage.albandrieu.com/")
    assert result["anonymous_http_status"] == 403
    assert result["cloudflare_default_deny"] is True
    assert result["cloudflare_service_auth_attempted"] is True
    assert result["cloudflare_service_token_access_passed"] is True
    assert result["public_probe_auth_mode"] == "cloudflare_service_token"
    assert result["reachable"] is True
    assert result["http_status"] == 200
    assert result["state"] == "ok"


@pytest.mark.asyncio
async def test_cloudflare_access_probe_stays_warning_when_service_token_is_blocked(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    monkeypatch.setattr(
        homelab_health,
        "_probe_http_edge_evidence",
        AsyncMock(
            return_value={
                "cloudflare_http_evidence": True,
                "cloudflare_access_signal": False,
                "cloudflare_default_deny": True,
                "http_evidence_status": 403,
                "http_probe_auth_mode": "anonymous",
                "cloudflare_service_auth_attempted": True,
                "cloudflare_service_token_access_passed": False,
                "cloudflare_service_token_http_status": 403,
            },
        ),
    )
    service = HomelabService(
        id="garage-webui",
        name="Garage",
        tunnelUrl="https://garage.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["http_status"] == 403
    assert result["state"] == "warn"
    assert result["cloudflare_default_deny"] is True
    assert result["cloudflare_service_token_access_passed"] is False


@pytest.mark.asyncio
async def test_probe_retries_get_when_head_is_not_supported() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        status = 405 if request.method == "HEAD" else 200
        return httpx.Response(status, request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert methods == ["HEAD", "GET"]
    assert result["http_status"] == 200
    assert result["state"] == "ok"


@pytest.mark.asyncio
async def test_probe_reports_tls_failure_as_red() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("certificate verify failed", request=request)

    service = HomelabService(
        name="Service",
        tunnelUrl="https://service.albandrieu.com",
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["reachable"] is False
    assert result["http_status"] == 0
    assert result["state"] == "fail"
    assert result["tls_trusted"] is False


@pytest.mark.asyncio
async def test_probe_fanout_budget_returns_partial_results(monkeypatch) -> None:
    fast = HomelabService(
        name="Fast internal",
        internalHost="192.0.2.10",
        internalPort=8080,
        external=False,
    )
    slow = HomelabService(
        name="Slow internal",
        internalHost="192.0.2.11",
        internalPort=8081,
        external=False,
    )

    async def fast_probe():
        return {
            "id": fast.service_id,
            "name": fast.name,
            "host": fast.internal_host,
            "port": fast.internal_port,
            "reachable": True,
            "state": "ok",
            "latency_ms": 1,
        }

    async def slow_probe():
        await asyncio.sleep(1)
        return {
            "id": slow.service_id,
            "name": slow.name,
            "host": slow.internal_host,
            "port": slow.internal_port,
            "reachable": True,
            "state": "ok",
            "latency_ms": 1000,
        }

    monkeypatch.setattr(homelab_health, "_SERVICE_FANOUT_BUDGET_SEC", 0.01)
    results, summary = await homelab_health._collect_bounded_probe_batch(
        [
            (fast, asyncio.create_task(fast_probe())),
            (slow, asyncio.create_task(slow_probe())),
        ],
        scope="internal",
    )

    assert summary["scheduled"] == 2
    assert summary["completed"] == 1
    assert summary["timed_out"] == 1
    assert summary["budget_seconds"] == 0.01
    assert summary["per_probe_timeout_seconds"] == 5.0
    assert summary["max_concurrency"] == 4
    assert results[0]["state"] == "ok"
    assert results[1]["timed_out"] is True
    assert results[1]["error_kind"] == "deadline"
