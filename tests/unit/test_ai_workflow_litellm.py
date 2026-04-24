"""LangGraph /run endpoint and LiteLLM (OpenAI-compatible) wiring for the workflow LLM."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from nabla.config_settings import DEFAULT_CHAT_MODEL, get_settings
from nabla.main import app


@pytest.fixture(autouse=True)
def clear_workflow_llm_cache() -> None:
    from nabla.ai import workflow as wf

    wf._get_workflow_llm.cache_clear()
    yield
    wf._get_workflow_llm.cache_clear()


def test_post_run_returns_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import workflow as wf

    def fake_safe_invoke(message: str) -> AIMessage:
        assert "LangGraph" in message
        return AIMessage(content="LangGraph is a graph-based orchestration layer for LLM apps.")

    monkeypatch.setattr(wf, "safe_invoke_llm", fake_safe_invoke)

    with TestClient(app) as client:
        res = client.post("/run", json={"user_input": "What is LangGraph?"})

    assert res.status_code == 200
    body = res.json()
    assert "result" in body
    assert "orchestration" in body["result"]


def test_post_run_returns_llm_result_person_question(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import workflow as wf

    def fake_safe_invoke(message: str) -> AIMessage:
        assert "Alban Andrieu" in message
        return AIMessage(
            content="Alban Andrieu is a software engineer focused on cloud orchestration.",
        )

    monkeypatch.setattr(wf, "safe_invoke_llm", fake_safe_invoke)

    with TestClient(app) as client:
        res = client.post("/run", json={"user_input": "Who is Alban Andrieu"})

    assert res.status_code == 200
    body = res.json()
    assert "result" in body
    assert "orchestration" in body["result"]


def test_workflow_llm_requests_gpt51_from_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import workflow as wf

    seen: list[str | None] = []

    def fake_build(*, model_name: str | None = None, **_kw: Any) -> MagicMock:
        seen.append(model_name if model_name is not None else get_settings().default_chat_model)
        return MagicMock()

    monkeypatch.setattr(wf, "build_chat_llm", fake_build)
    wf._get_workflow_llm()
    assert seen == [get_settings().default_chat_model]


def test_workflow_llm_uses_litellm_openai_compatible_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import llm_factory as lf
    from nabla.ai import workflow as wf

    fake = SimpleNamespace(
        litellm_url="http://litellm.test:4000",
        litellm_api_key=SecretStr("sk-litellm-test"),
        azure_openai_instance={},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)

    mock_ctor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(lf, "_ChatOpenAI", mock_ctor)

    out = wf._get_workflow_llm()
    assert out is mock_ctor.return_value
    mock_ctor.assert_called_once()
    kwargs = mock_ctor.call_args.kwargs
    assert kwargs["model"] == DEFAULT_CHAT_MODEL
    assert kwargs["openai_api_base"] == "http://litellm.test:4000/v1"
    assert kwargs["openai_api_key"] == "sk-litellm-test"
