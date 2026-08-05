"""Tests for the authenticated Supabase health probe."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from nabla.api import health_checks


@pytest.mark.asyncio
async def test_supabase_health_sends_service_role_key(monkeypatch) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_service_role_key=SecretStr("service-key"),
    )
    response = httpx.Response(200, request=httpx.Request("GET", "https://project.supabase.co"))
    get = AsyncMock(return_value=response)

    monkeypatch.setattr(health_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    result = await health_checks.check_supabase_http()

    assert result == {"reachable": True, "http_status": 200}
    assert get.call_args.kwargs["headers"] == {
        "apikey": "service-key",
        "Authorization": "Bearer service-key",
    }


@pytest.mark.asyncio
async def test_supabase_unauthorized_is_not_healthy(monkeypatch) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_service_role_key=None,
    )
    response = httpx.Response(401, request=httpx.Request("GET", "https://project.supabase.co"))

    monkeypatch.setattr(health_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))

    assert await health_checks.check_supabase_http() == {
        "reachable": False,
        "http_status": 401,
    }
