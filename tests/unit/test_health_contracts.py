"""Contracts for liveness, readiness, and deep diagnostics."""

from unittest.mock import Mock

import pytest

from nabla.api import health_contracts


def test_liveness_never_depends_on_external_services() -> None:
    payload = health_contracts.build_liveness_payload(version="1.2.3")

    assert payload["contract"] == "liveness"
    assert payload["status"] == "alive"
    assert payload["version"] == "1.2.3"
    assert "checks" not in payload


@pytest.mark.asyncio
async def test_readiness_reports_required_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        health_contracts,
        "check_postgres_sql",
        Mock(return_value={"reachable": True}),
    )

    async def redis_failure(_client):
        return {"reachable": False, "error": "unavailable"}

    monkeypatch.setattr(health_contracts, "check_redis_ping", redis_failure)

    payload, ready = await health_contracts.build_readiness_payload(
        redis_client=Mock(),
        engine=Mock(),
        version="test",
    )

    assert ready is False
    assert payload["contract"] == "readiness"
    assert payload["status"] == "not_ready"


def test_deep_diagnostic_distinguishes_optional_degradation() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "pfsense": {"reachable": False},
            },
        },
    )

    assert payload["contract"] == "deep_diagnostic"
    assert payload["status"] == "degraded"
