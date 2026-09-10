"""Regression tests for optional health-probe cadence and telemetry metadata."""

import pytest

from nabla.api import health_probe_cadence


@pytest.fixture(autouse=True)
def _reset_probe_cache() -> None:
    health_probe_cadence.reset_probe_cadence_cache()


@pytest.mark.asyncio
async def test_configured_optional_probe_is_reused_between_health_refreshes() -> None:
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {"reachable": True}

    first = await health_probe_cadence.run_cadenced_optional_probe("tavily", loader)
    second = await health_probe_cadence.run_cadenced_optional_probe("tavily", loader)

    assert calls == 1
    assert first["probe_source"] == "origin"
    assert first["probe_interval_seconds"] == 300.0
    assert second["probe_source"] == "memory"
    assert second["probe_observed_at"] == first["probe_observed_at"]
    assert second["next_probe_in_seconds"] <= 300.0


@pytest.mark.asyncio
async def test_unconfigured_optional_probe_uses_fifteen_minute_cadence() -> None:
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return {
            "reachable": None,
            "skipped": True,
            "reason": "TAVILY_API_KEY not configured",
        }

    first = await health_probe_cadence.run_cadenced_optional_probe("tavily", loader)
    second = await health_probe_cadence.run_cadenced_optional_probe("tavily", loader)

    assert calls == 1
    assert first["probe_interval_seconds"] == 900.0
    assert second["probe_source"] == "memory"


@pytest.mark.asyncio
async def test_failed_optional_probe_retries_after_one_minute() -> None:
    async def loader():
        return {"reachable": False, "error": "provider unavailable"}

    result = await health_probe_cadence.run_cadenced_optional_probe("brave", loader)

    assert result["probe_interval_seconds"] == 60.0
    assert result["next_probe_in_seconds"] <= 60.0


@pytest.mark.asyncio
async def test_local_support_probe_uses_two_minute_cadence() -> None:
    async def loader():
        return {"reachable": True}

    result = await health_probe_cadence.run_cadenced_optional_probe("pyroscope", loader)

    assert result["probe_interval_seconds"] == 120.0


def test_required_probe_is_annotated_without_optional_cache() -> None:
    result = health_probe_cadence.annotate_required_probe(
        "postgres",
        {"reachable": True},
    )

    assert result["probe_source"] == "origin"
    assert result["probe_interval_seconds"] == 30.0
    assert result["probe_age_seconds"] == 0.0
