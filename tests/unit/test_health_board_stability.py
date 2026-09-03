"""Regression tests for aggregate diagnostic deadlines."""

import asyncio
from types import SimpleNamespace

import pytest

from nabla.api import health_board
from nabla.api import health_checks
from nabla.api import observability_health
from nabla.api import platform_health
from nabla.api import sickz_checks
from nabla.api import sickz_policy


def _request():
    return SimpleNamespace(app=SimpleNamespace(version="test"))


@pytest.mark.asyncio
async def test_healthz_optional_enrichment_returns_timeout_evidence(monkeypatch) -> None:
    async def base_payload(_request, *, redis_client, engine):
        del redis_client, engine
        return {"checks": {}, "version": "test"}

    async def slow_enrichment(payload):
        await asyncio.sleep(1.0)
        return payload

    monkeypatch.setattr(health_checks, "build_healthz_payload", base_payload)
    monkeypatch.setattr(
        platform_health,
        "enrich_optional_platform_checks",
        slow_enrichment,
    )
    monkeypatch.setattr(
        observability_health,
        "enrich_optional_observability_checks",
        slow_enrichment,
    )
    monkeypatch.setattr(
        health_board,
        "_HEALTHZ_OPTIONAL_ENRICHMENT_DEADLINE_SEC",
        0.01,
    )

    payload = await health_board.build_extended_healthz(_request())

    assert payload["checks"]["pfsense"]["timed_out"] is True
    assert payload["checks"]["cloudflare"]["error_kind"] == "deadline"
    assert payload["checks"]["logfire"]["error_kind"] == "deadline"


@pytest.mark.asyncio
async def test_sickz_policy_timeout_keeps_low_level_payload(monkeypatch) -> None:
    async def low_level(_request):
        return {"checks": {"service": {"reachable": True}}, "version": "test"}

    async def slow_policy(payload):
        await asyncio.sleep(1.0)
        return payload

    monkeypatch.setattr(sickz_checks, "build_sickz_payload", low_level)
    monkeypatch.setattr(sickz_policy, "enrich_sickz_policy", slow_policy)
    monkeypatch.setattr(health_board, "_SICKZ_POLICY_DEADLINE_SEC", 0.01)

    payload = await health_board.build_sickz_snapshot(_request())

    assert payload["checks"]["service"]["reachable"] is True
    assert payload["policy_enrichment"]["status"] == "timeout"
    assert payload["policy_enrichment"]["error_kind"] == "deadline"


@pytest.mark.asyncio
async def test_homelab_snapshot_returns_degraded_timeout_payload(monkeypatch) -> None:
    async def slow_snapshot(_shared_checks=None):
        await asyncio.sleep(1.0)
        return {"status": "ok"}

    monkeypatch.setattr(health_board, "_build_homelab_snapshot", slow_snapshot)
    monkeypatch.setattr(health_board, "_HOMELAB_SNAPSHOT_DEADLINE_SEC", 0.01)

    payload = await health_board.build_homelab_snapshot()

    assert payload["status"] == "degraded"
    assert payload["timed_out"] is True
    assert payload["error_kind"] == "deadline"


@pytest.mark.asyncio
async def test_health_board_refresh_deadline_does_not_pin_task(monkeypatch) -> None:
    async def slow_board(_request):
        await asyncio.sleep(1.0)
        return {"schema_version": 1}

    await health_board.reset_health_board_cache()
    monkeypatch.setattr(health_board, "build_health_board_snapshot", slow_board)
    monkeypatch.setattr(health_board, "_HEALTH_BOARD_REFRESH_DEADLINE_SEC", 0.01)

    await health_board._refresh(_request())

    assert health_board._last_refresh_error == "health board refresh deadline exceeded"
    await health_board.reset_health_board_cache()
