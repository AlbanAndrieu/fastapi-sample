"""Fail-closed contracts for owner-only OpenRAG Bababou retrieval."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from nabla.api import private_bababou_search as subject
from nabla.route_policy import Credential, Visibility, route_policy_for


def _mcp(*, url="http://openrag-frontend:3000/mcp", key="orag-private-synthetic",
         transport="streamable-http", enabled=True):
    return SimpleNamespace(
        name="openrag", url=url, transport=transport, enabled=enabled,
        headers={"X-API-Key": key},
    )


def test_owner_search_has_jwt_policy_and_no_public_alias():
    policy = route_policy_for("/private/ops/ai/bababou/search", method="POST")
    assert policy.visibility is Visibility.OWNER
    assert policy.credential is Credential.ACCESS_JWT
    assert route_policy_for("/run", method="POST").visibility is Visibility.REVIEW
    assert subject.router.prefix == "/private/ops/ai"


def test_bababou_search_request_is_bounded():
    with pytest.raises(ValidationError):
        subject.BababouSearch(query="x", limit=5)
    with pytest.raises(ValidationError):
        subject.BababouSearch(query="e" * 301, limit=5)
    with pytest.raises(ValidationError):
        subject.BababouSearch(query="bababou", limit=6)


def test_auth_config_requires_scoped_filter_and_private_transport(monkeypatch):
    monkeypatch.setattr(subject, "get_settings", lambda: SimpleNamespace(mcp_clients=[_mcp()]))
    monkeypatch.delenv("OPENRAG_BABABOU_FILTER_ID", raising=False)
    assert subject.search_configuration_ready() is False
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    assert subject.search_configuration_ready() is True

    for changed in [
        _mcp(url="https://untrusted.example/mcp"),
        _mcp(key=""),
        _mcp(transport="stdio"),
        _mcp(enabled=False),
    ]:
        monkeypatch.setattr(subject, "get_settings",
                            lambda changed=changed: SimpleNamespace(mcp_clients=[changed]))
        assert subject.search_configuration_ready() is False


def test_duplicate_clients_are_rejected(monkeypatch):
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    monkeypatch.setattr(subject, "get_settings",
                        lambda: SimpleNamespace(mcp_clients=[_mcp(), _mcp()]))
    assert subject.search_configuration_ready() is False


def test_missing_config_never_queries_mcp(monkeypatch):
    monkeypatch.setattr(subject, "search_configuration_ready", lambda: False)
    async def unavailable(*args):
        raise AssertionError("MCP must not be called")
    monkeypatch.setattr(subject, "mcp_call_tool", unavailable)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(subject.search_bababou(subject.BababouSearch(query="éléonore")))
    assert exc.value.status_code == 503


def test_owner_search_only_calls_scoped_search_and_redacts_paths(monkeypatch):
    monkeypatch.setattr(subject, "search_configuration_ready", lambda: True)
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    calls = []
    async def fake_search(name, tool, arguments):
        calls.append((name, tool, arguments))
        return {"results": [{
            "source_path": "/mnt/cpool/bababou/confidential.pdf",
            "snippet": "Evidence in /mnt/cpool/bababou/confidential.pdf",
            "page": 2,
        }]}
    monkeypatch.setattr(subject, "mcp_call_tool", fake_search)
    result = asyncio.run(subject.search_bababou(
        subject.BababouSearch(query="Documents concernant Éléonore", limit=3)
    ))
    assert result.status_code == 200
    assert calls == [(
        "openrag", "openrag_search",
        {"query": "Documents concernant Éléonore", "limit": 3,
         "filter_id": "bababou-filter-123"},
    )]
    assert result.headers["cache-control"] == "private, no-store"
    payload = json.loads(result.body)
    assert payload["status"] == "retrieved"
    assert "source_path" not in json.dumps(payload)
    assert "/mnt/cpool/" not in json.dumps(payload)


def test_mcp_errors_do_not_return_secret_or_private_text(monkeypatch):
    monkeypatch.setattr(subject, "search_configuration_ready", lambda: True)
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    async def failure(*args):
        raise RuntimeError("OpenRAG secret=do-not-expose /mnt/cpool/bababou/private")
    monkeypatch.setattr(subject, "mcp_call_tool", failure)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(subject.search_bababou(subject.BababouSearch(query="éléonore")))
    assert exc.value.status_code == 502
    assert "do-not-expose" not in str(exc.value.detail)


def test_oversized_mcp_output_fails_closed(monkeypatch):
    monkeypatch.setattr(subject, "search_configuration_ready", lambda: True)
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    async def huge(*args):
        return {"content": ["x" * 16_000, "y" * 16_000]}
    monkeypatch.setattr(subject, "mcp_call_tool", huge)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(subject.search_bababou(subject.BababouSearch(query="éléonore")))
    assert exc.value.status_code == 502


def test_general_agent_tools_do_not_automatically_activate(monkeypatch):
    from nabla.integrations import openrag_mcp_tools
    monkeypatch.delenv("OPENRAG_GENERAL_MCP_TOOLS_ENABLED", raising=False)
    monkeypatch.setattr(openrag_mcp_tools, "get_settings",
                        lambda: SimpleNamespace(mcp_clients=[_mcp()]))
    assert openrag_mcp_tools.build_openrag_mcp_tools() == []



def test_private_filter_cannot_enable_general_agent_even_with_opt_in(monkeypatch):
    from nabla.integrations import openrag_mcp_tools
    monkeypatch.setenv("OPENRAG_GENERAL_MCP_TOOLS_ENABLED", "true")
    monkeypatch.setenv("OPENRAG_BABABOU_FILTER_ID", "bababou-filter-123")
    monkeypatch.setattr(openrag_mcp_tools, "get_settings",
                        lambda: SimpleNamespace(mcp_clients=[_mcp()]))
    assert openrag_mcp_tools.build_openrag_mcp_tools() == []
