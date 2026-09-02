"""Tests for shared core/platform component-health composition."""

from unittest.mock import AsyncMock, Mock

import pytest

from nabla.api import component_health


@pytest.mark.asyncio
async def test_component_checks_compose_core_and_platform_without_service_rows(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        component_health,
        "check_postgres_sql",
        Mock(return_value={"reachable": True}),
    )
    monkeypatch.setattr(
        component_health,
        "check_redis_ping",
        AsyncMock(return_value={"reachable": True}),
    )
    monkeypatch.setattr(
        component_health,
        "check_supabase_http",
        AsyncMock(return_value={"reachable": True}),
    )
    monkeypatch.setattr(
        component_health,
        "build_homelab_health_payload",
        AsyncMock(
            return_value={
                "truenas": {
                    "state": "ok",
                    "public": {
                        "reachable": True,
                        "http_status": 200,
                        "tls_trusted": True,
                    },
                    "internal": None,
                    "api": {"reachable": True},
                },
                "services": [{"name": "must-not-leak"}],
            },
        ),
    )
    monkeypatch.setattr(
        component_health,
        "check_cloudflare_tunnels",
        AsyncMock(return_value={"reachable": True, "tunnel_count": 2}),
    )
    monkeypatch.setattr(
        component_health,
        "get_pfsense_api_snapshot",
        AsyncMock(return_value={"reachable": True}),
    )

    components = await component_health.build_component_checks(
        redis_client=Mock(),
        engine=Mock(),
    )

    assert list(components) == [
        "postgres",
        "redis",
        "supabase",
        "truenas",
        "cloudflare",
        "pfsense",
    ]
    assert components["truenas"] == {
        "reachable": True,
        "state": "ok",
        "public_reachable": True,
        "internal_reachable": None,
        "api_reachable": True,
        "tls_trusted": True,
        "http_status": 200,
    }
    assert "services" not in components


def test_component_status_keeps_optional_platform_failure_nonfatal() -> None:
    components = {
        "postgres": {"reachable": True},
        "redis": {"reachable": True},
        "supabase": {"reachable": True},
        "truenas": {"reachable": False},
        "cloudflare": {"reachable": True},
        "pfsense": {"skipped": True, "reachable": None},
    }

    assert component_health.component_status(components) == "degraded"


def test_component_status_marks_core_failure_unhealthy() -> None:
    components = {
        "postgres": {"reachable": False},
        "redis": {"reachable": True},
        "supabase": {"reachable": True},
    }

    assert component_health.component_status(components) == "unhealthy"
