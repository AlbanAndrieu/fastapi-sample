"""Contracts for request-scoped reuse of rich homelab provider observations."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nabla.api import homelab_provider_reuse
from nabla.api.cloudflare_exposure_observer import CloudflareExposureSnapshot
from nabla.api.cloudflare_tunnels import CloudflareTunnelObservation


def _cloudflare(*, stale: bool = False) -> CloudflareExposureSnapshot:
    return CloudflareExposureSnapshot(
        configured=True,
        tunnels=(
            CloudflareTunnelObservation(
                tunnel_id="healthy",
                name="healthy",
                status="healthy",
            ),
            CloudflareTunnelObservation(
                tunnel_id="retired",
                name="retired",
                status="inactive",
            ),
        ),
        stale=stale,
        refresh_error="refresh timeout" if stale else None,
    )


def test_cloudflare_health_reuses_rich_tunnel_inventory() -> None:
    result = homelab_provider_reuse.cloudflare_health_from_exposure(_cloudflare())

    assert result["reachable"] is True
    assert result["status_confirmed"] is True
    assert result["state"] == "ok"
    assert result["tunnel_count"] == 2
    assert result["healthy_tunnels"] == 1
    assert result["inactive_tunnels"] == 1
    assert result["inventory_attention"] is True
    assert result["reused_from"] == "cloudflare_exposure"


def test_cloudflare_stale_exposure_remains_unknown_not_down() -> None:
    result = homelab_provider_reuse.cloudflare_health_from_exposure(
        _cloudflare(stale=True),
    )

    assert result["reachable"] is None
    assert result["status_confirmed"] is False
    assert result["state"] == "unknown"
    assert result["degraded"] is False
    assert result["stale"] is True
    assert "could not be confirmed" in result["warning"]


def test_pfsense_health_reuses_successful_system_endpoint() -> None:
    result = homelab_provider_reuse.pfsense_health_from_posture(
        {
            "configured": True,
            "endpoint_status": {
                "system": {"observed": True},
                "services": {"observed": True},
            },
        },
    )

    assert result is not None
    assert result["reachable"] is True
    assert result["status_confirmed"] is True
    assert result["state"] == "ok"
    assert result["path"] == "/api/v2/system/version"
    assert result["reused_from"] == "pfsense_posture"


@pytest.mark.asyncio
async def test_pfsense_reuse_falls_back_only_without_system_endpoint(monkeypatch) -> None:
    fallback = AsyncMock(return_value={"reachable": None, "status_confirmed": False})
    monkeypatch.setattr(
        homelab_provider_reuse,
        "get_pfsense_api_snapshot",
        fallback,
    )
    context = {
        "cloudflare": _cloudflare(),
        "pfsense_dns": {
            "configured": True,
            "endpoint_status": {"system": {"observed": False, "error": "timeout"}},
        },
    }

    result = await homelab_provider_reuse.platform_checks_from_reconciliation_context(
        context,
    )

    fallback.assert_awaited_once_with()
    assert result["cloudflare"]["reused_from"] == "cloudflare_exposure"
    assert result["pfsense"]["status_confirmed"] is False
