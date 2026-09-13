"""Regression tests for health-board request-scoped provider reuse."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nabla.api import health_board, health_checks, observability_health, platform_health
from nabla.api.cloudflare_exposure_observer import CloudflareExposureSnapshot
from nabla.api.cloudflare_tunnels import CloudflareTunnelObservation


def _request():
    return SimpleNamespace(
        app=SimpleNamespace(version="test"),
        url=SimpleNamespace(hostname="localhost"),
    )


def _context() -> dict[str, object]:
    return {
        "cloudflare": CloudflareExposureSnapshot(
            configured=True,
            tunnels=(
                CloudflareTunnelObservation(
                    tunnel_id="tunnel",
                    name="tunnel",
                    status="healthy",
                ),
            ),
        ),
        "pfsense_dns": {
            "configured": True,
            "endpoint_status": {"system": {"observed": True}},
        },
    }


async def _base_payload(_request, *, redis_client, engine):
    del redis_client, engine
    return {"checks": {}, "version": "test"}


async def _observability_passthrough(payload):
    return {**payload, "checks": {**payload.get("checks", {}), "logfire": {"reachable": True}}}


@pytest.mark.asyncio
async def test_healthz_reuses_shared_provider_context_without_lightweight_reads(
    monkeypatch,
) -> None:
    standalone = AsyncMock(side_effect=AssertionError("standalone provider checks must not run"))
    monkeypatch.setattr(health_checks, "build_healthz_payload", _base_payload)
    monkeypatch.setattr(
        observability_health,
        "enrich_optional_observability_checks",
        _observability_passthrough,
    )
    monkeypatch.setattr(platform_health, "enrich_optional_platform_checks", standalone)
    context_task = asyncio.create_task(asyncio.sleep(0, result=_context()))

    payload = await health_board.build_extended_healthz(
        _request(),
        reconciliation_context=context_task,
    )

    standalone.assert_not_awaited()
    assert payload["checks"]["cloudflare"]["reused_from"] == "cloudflare_exposure"
    assert payload["checks"]["pfsense"]["reused_from"] == "pfsense_posture"


@pytest.mark.asyncio
async def test_healthz_subdeadline_does_not_cancel_shared_provider_context(
    monkeypatch,
) -> None:
    monkeypatch.setattr(health_checks, "build_healthz_payload", _base_payload)
    monkeypatch.setattr(
        observability_health,
        "enrich_optional_observability_checks",
        _observability_passthrough,
    )
    monkeypatch.setattr(
        health_board,
        "_HEALTHZ_OPTIONAL_ENRICHMENT_DEADLINE_SEC",
        0.01,
    )

    async def delayed_context():
        await asyncio.sleep(0.03)
        return _context()

    context_task = asyncio.create_task(delayed_context())
    payload = await health_board.build_extended_healthz(
        _request(),
        reconciliation_context=context_task,
    )

    assert payload["checks"]["cloudflare"]["error_kind"] == "deadline"
    assert payload["checks"]["pfsense"]["timed_out"] is True
    assert context_task.cancelled() is False
    assert await context_task == _context()


@pytest.mark.asyncio
async def test_standalone_healthz_keeps_lightweight_platform_path(monkeypatch) -> None:
    platform = AsyncMock(
        return_value={
            "checks": {
                "cloudflare": {"reachable": True},
                "pfsense": {"reachable": True},
            },
        },
    )
    monkeypatch.setattr(health_checks, "build_healthz_payload", _base_payload)
    monkeypatch.setattr(
        observability_health,
        "enrich_optional_observability_checks",
        _observability_passthrough,
    )
    monkeypatch.setattr(platform_health, "enrich_optional_platform_checks", platform)

    payload = await health_board.build_extended_healthz(_request())

    platform.assert_awaited_once()
    assert payload["checks"]["cloudflare"]["reachable"] is True
    assert payload["checks"]["pfsense"]["reachable"] is True
