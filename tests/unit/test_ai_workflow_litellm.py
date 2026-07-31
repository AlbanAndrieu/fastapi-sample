"""LangGraph /run endpoint and LiteLLM (OpenAI-compatible) wiring for the workflow LLM."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from nabla.config_settings import DEFAULT_CHAT_MODEL, get_settings
from nabla.deepagents import workflow as wf

import nabla.config_settings as config_settings
import nabla.deepagents.llm_factory as llm_factory


@pytest.fixture(autouse=True)
def clear_workflow_llm_cache() -> None:
    wf._get_workflow_llm.cache_clear()
    wf._build_workflow_agent.cache_clear()
    yield
    wf._get_workflow_llm.cache_clear()
    wf._build_workflow_agent.cache_clear()


async def _run_inline(func: Any) -> Any:
    """Unit tests do not need the production thread-pool boundary."""
    return func()


def _workflow_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wf.router)
    return app


@pytest.mark.asyncio
async def test_post_run_returns_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_safe_invoke(message: str) -> str:
        assert "LangGraph" in message
        return "LangGraph is a graph-based orchestration layer for LLM apps."

    monkeypatch.setattr(wf, "safe_invoke_llm", fake_safe_invoke)
    monkeypatch.setattr(wf.anyio.to_thread, "run_sync", _run_inline)
    async with AsyncClient(transport=ASGITransport(app=_workflow_test_app()), base_url="http://test") as client:
        res = await client.post("/run", json={"user_input": "What is LangGraph?"})
    assert res.status_code == 200
    body = res.json()
    assert "result" in body
    assert "orchestration" in body["result"]


@pytest.mark.asyncio
async def test_post_run_returns_llm_result_person_question(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_safe_invoke(message: str) -> str:
        assert "Alban Andrieu" in message
        return "Alban Andrieu is a software engineer focused on cloud orchestration."

    monkeypatch.setattr(wf, "safe_invoke_llm", fake_safe_invoke)
    monkeypatch.setattr(wf.anyio.to_thread, "run_sync", _run_inline)
    async with AsyncClient(transport=ASGITransport(app=_workflow_test_app()), base_url="http://test") as client:
        res = await client.post("/run", json={"user_input": "Who is Alban Andrieu"})
    assert res.status_code == 200
    body = res.json()
    assert "result" in body
    assert "orchestration" in body["result"]


def test_workflow_llm_requests_gpt51_from_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    def fake_build(*, model_name: str | None = None, **_kw: Any) -> MagicMock:
        seen.append(model_name if model_name is not None else get_settings().default_chat_model)
        return MagicMock()

    monkeypatch.setattr(wf, "build_chat_llm", fake_build)
    wf._get_workflow_llm()
    assert seen == [get_settings().default_chat_model]


def test_workflow_llm_uses_litellm_openai_compatible_client(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="http://litellm.test:4000",
        litellm_api_key=SecretStr("sk-litellm-test"),
        azure_openai_instance={},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )

    monkeypatch.setattr(config_settings, "get_settings", lambda: fake)
    mock_ctor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(llm_factory, "_ChatOpenAI", mock_ctor)

    out = wf._get_workflow_llm()
    assert out is mock_ctor.return_value
    mock_ctor.assert_called_once()
    kwargs = mock_ctor.call_args.kwargs
    assert kwargs["model"] == DEFAULT_CHAT_MODEL
    assert kwargs["openai_api_base"].endswith("/v1")
    assert ":4000" in kwargs["openai_api_base"]
    assert kwargs["openai_api_key"].startswith("sk-")
    assert len(kwargs["openai_api_key"]) > 10
