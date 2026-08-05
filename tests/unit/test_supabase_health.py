"""Tests for the authenticated Supabase Data API health probe."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from nabla.api import health_checks


@pytest.mark.asyncio
async def test_supabase_health_prefers_publishable_key(monkeypatch) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_publishable_key=SecretStr("publishable-key"),
        supabase_service_role_key=SecretStr("service-key"),
        supabase_health_table="note",
    )
    response = httpx.Response(200, request=httpx.Request("GET", "https://project.supabase.co"))
    get = AsyncMock(return_value=response)

    monkeypatch.setattr(health_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    result = await health_checks.check_supabase_http()

    assert result == {
        "reachable": True,
        "http_status": 200,
        "probe": "data_api",
        "authentication": "publishable_key",
        "resource": "note",
        "path": "/rest/v1/note",
    }
    assert get.call_args.args[0] == "https://project.supabase.co/rest/v1/note"
    assert get.call_args.kwargs["params"] == {"select": "id", "limit": "0"}
    assert get.call_args.kwargs["headers"] == {
        "apikey": "publishable-key",
        "Accept": "application/json",
    }


@pytest.mark.asyncio
async def test_supabase_unauthorized_is_not_healthy(monkeypatch) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_publishable_key=SecretStr("rejected-key"),
        supabase_service_role_key=None,
        supabase_health_table="note",
    )
    response = httpx.Response(401, request=httpx.Request("GET", "https://project.supabase.co"))

    monkeypatch.setattr(health_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))

    assert await health_checks.check_supabase_http() == {
        "reachable": False,
        "http_status": 401,
        "probe": "data_api",
        "authentication": "publishable_key",
        "resource": "note",
        "path": "/rest/v1/note",
    }


@pytest.mark.asyncio
async def test_supabase_health_falls_back_to_service_role_key(monkeypatch) -> None:
    settings = SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_publishable_key=None,
        supabase_service_role_key=SecretStr("service-key"),
        supabase_health_table="note",
    )
    response = httpx.Response(200, request=httpx.Request("GET", "https://project.supabase.co"))
    get = AsyncMock(return_value=response)

    monkeypatch.setattr(health_checks, "get_settings", lambda: settings)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    result = await health_checks.check_supabase_http()

    assert result["authentication"] == "service_role_key"
    assert get.call_args.kwargs["headers"] == {
        "apikey": "service-key",
        "Accept": "application/json",
    }
