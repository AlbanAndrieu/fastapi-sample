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


def test_optional_deadline_is_unknown_warning_not_degradation() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "garage": {
                    "reachable": False,
                    "timed_out": True,
                    "error_kind": "deadline",
                    "error": "aggregate health probe deadline exceeded",
                },
            },
        },
    )

    assert payload["status"] == "healthy"
    assert payload["checks"]["garage"]["reachable"] is None
    assert payload["checks"]["garage"]["status_confirmed"] is False
    assert payload["checks"]["garage"]["severity"] == "warning"
    assert payload["checks"]["garage"]["effective_state"] == "warn"
    assert payload["checks"]["garage"]["warning"].startswith("⚠️")


def test_cloudflare_retrieval_failure_is_unconfirmed_not_degraded() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "cloudflare": {
                    "reachable": False,
                    "api_reachable": False,
                    "error_kind": "connect_timeout",
                    "error": "connection timed out",
                    "probe": "cloudflare_tunnel_api",
                },
            },
        },
    )

    cloudflare = payload["checks"]["cloudflare"]
    assert payload["status"] == "healthy"
    assert cloudflare["reachable"] is None
    assert cloudflare["degraded"] is False
    assert cloudflare["status_confirmed"] is False
    assert cloudflare["effective_state"] == "warn"
    assert "Cloudflare global status could not be confirmed" in cloudflare["warning"]
    assert "connection timed out" in cloudflare["error"]


def test_stale_cloudflare_inventory_is_context_not_current_health() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "cloudflare": {
                    "reachable": True,
                    "api_reachable": True,
                    "tunnel_count": 2,
                    "healthy_tunnels": 2,
                    "unhealthy_tunnels": 0,
                    "tunnel_statuses": ["healthy", "healthy"],
                    "stale": True,
                    "refresh_error": "read timeout",
                },
            },
        },
    )

    cloudflare = payload["checks"]["cloudflare"]
    assert payload["status"] == "healthy"
    assert cloudflare["reachable"] is None
    assert cloudflare["last_known_reachable"] is True
    assert cloudflare["status_confirmed"] is False
    assert cloudflare["degraded"] is False
    assert cloudflare["effective_state"] == "warn"
    assert "Cloudflare global status could not be confirmed" in cloudflare["error"]
    assert "read timeout" in cloudflare["error"]


def test_unconfigured_cloudflare_is_warning_not_degradation() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "cloudflare": {
                    "reachable": None,
                    "skipped": True,
                    "reason": "Cloudflare credentials are not configured",
                    "probe": "cloudflare_tunnel_api",
                },
            },
        },
    )

    cloudflare = payload["checks"]["cloudflare"]
    assert payload["status"] == "healthy"
    assert cloudflare["reachable"] is None
    assert cloudflare["status_confirmed"] is False
    assert cloudflare["effective_state"] == "warn"
    assert cloudflare["reason"].startswith("⚠️ Cloudflare global status could not be confirmed")


def test_confirmed_unhealthy_cloudflare_inventory_still_degrades() -> None:
    payload = health_contracts.apply_diagnostic_status(
        {
            "checks": {
                "postgres": {"reachable": True},
                "redis": {"reachable": True},
                "supabase": {"reachable": True},
                "cloudflare": {
                    "reachable": False,
                    "api_reachable": True,
                    "tunnel_count": 2,
                    "healthy_tunnels": 1,
                    "unhealthy_tunnels": 1,
                    "tunnel_statuses": ["healthy", "down"],
                    "degraded": True,
                },
            },
        },
    )

    assert payload["status"] == "degraded"
    assert payload["checks"]["cloudflare"]["reachable"] is False
    assert payload["checks"]["cloudflare"]["degraded"] is True
