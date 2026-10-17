"""Contract tests for Cloudflare Access evidence in public homelab probes.

An Access redirect or refusal is edge evidence only: it must never be reported
as a healthy origin, and a rejected service token is a distinct diagnostic.
"""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from nabla.api import homelab_health
from nabla.api.homelab_models import HomelabService


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
            "origin_reached": True,
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
async def test_protected_public_probe_without_edge_confirmation_remains_warning(
    monkeypatch,
) -> None:
    """An anonymous HTTP 403 is not evidence that the application is healthy."""
    edge_probe = AsyncMock(
        return_value={
            "cloudflare_service_token_access_passed": False,
            "cloudflare_default_deny": False,
            "cloudflare_access_signal": False,
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
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, request=request),
        ),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["state"] == "warn"
    assert result["public_probe_auth_mode"] == "cloudflare_access_unconfirmed"
    assert result["public_probe_verification"] == "origin_unverified"
    assert result["origin_reached"] is False


@pytest.mark.asyncio
async def test_missing_authenticated_http_status_does_not_claim_failure(
    monkeypatch,
) -> None:
    edge_probe = AsyncMock(
        return_value={
            "cloudflare_service_token_access_passed": True,
            "origin_reached": False,
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
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, request=request),
        ),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )

    assert result["http_status"] == 0
    assert result["state"] == "warn"
    assert result["public_probe_verification"] == "authenticated_origin_unverified"


@pytest.mark.asyncio
async def test_access_success_without_origin_evidence_does_not_report_healthy(
    monkeypatch,
) -> None:
    edge = AsyncMock(
        return_value={
            "cloudflare_service_token_access_passed": True,
            "authenticated_http_status": 200,
            "origin_reached": False,
        },
    )
    monkeypatch.setattr(homelab_health, "_probe_http_edge_evidence", edge)
    service = HomelabService(
        id="garage-webui",
        name="Garage",
        tunnelUrl="https://garage.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, request=request),
        ),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )
    assert result["state"] == "warn"
    assert result["origin_reached"] is False
    assert result["public_probe_verification"] == "authenticated_origin_unverified"


@pytest.mark.asyncio
async def test_access_token_rejection_is_explicit_diagnostic_not_origin_down(
    monkeypatch,
) -> None:
    edge = AsyncMock(
        return_value={
            "cloudflare_default_deny": True,
            "cloudflare_service_auth_attempted": True,
            "cloudflare_service_token_access_passed": False,
            "cloudflare_service_token_http_status": 403,
        },
    )
    monkeypatch.setattr(homelab_health, "_probe_http_edge_evidence", edge)
    service = HomelabService(
        id="garage-webui",
        name="Garage",
        tunnelUrl="https://garage.albandrieu.com",
        tunnelSecure=True,
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, request=request),
        ),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(
            client,
            asyncio.Semaphore(1),
            service,
        )
    assert result["cloudflare_service_token_rejected"] is True
    assert result["origin_reached"] is False
    assert result["state"] == "warn"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tunnel_secure", "status", "eligible"),
    [
        (True, 302, True),
        (True, 403, True),
        (True, 200, False),
        (False, 302, False),
    ],
)
async def test_access_secondary_probe_eligibility_is_explicit(
    monkeypatch,
    tunnel_secure: bool,
    status: int,
    eligible: bool,
) -> None:
    """Only an Access-required service answering with an edge status is re-probed."""
    edge_probe = AsyncMock(return_value={"cloudflare_access_signal": True})
    monkeypatch.setattr(homelab_health, "_probe_http_edge_evidence", edge_probe)
    service = HomelabService(
        id="ittools",
        name="IT Tools",
        tunnelUrl="https://ittools.albandrieu.com",
        tunnelSecure=tunnel_secure,
        external=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, request=request)),
        follow_redirects=False,
    ) as client:
        result = await homelab_health._probe_public_service(client, asyncio.Semaphore(1), service)

    assert result["cloudflare_access_secondary_probe_eligible"] is eligible
    assert result["cloudflare_access_secondary_probe_attempted"] is eligible
    assert edge_probe.await_count == (1 if eligible else 0)
    if eligible:
        assert result["public_probe_verification"] == "access_protected_origin_unverified"
        assert result["public_probe_auth_mode"] == "cloudflare_access_blocked"
        assert result["state"] == "warn"
