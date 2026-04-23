"""LangGraph /run endpoint and LiteLLM (OpenAI-compatible) wiring for the workflow LLM."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr

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


def test_workflow_llm_requests_gpt51_from_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import workflow as wf

    seen: list[str] = []

    def fake_build(*, model_name: str = "gpt-5.1") -> MagicMock:
        seen.append(model_name)
        return MagicMock()

    monkeypatch.setattr(wf, "build_chat_llm", fake_build)
    wf._get_workflow_llm()
    assert seen == ["gpt-5.1"]


def test_workflow_llm_uses_litellm_openai_compatible_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from nabla.ai import llm_factory as lf
    from nabla.ai import workflow as wf

    fake = SimpleNamespace(
        litellm_url="http://litellm.test:4000",
        litellm_api_key=SecretStr("sk-litellm-test"),
        azure_openai_instance={},
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)

    mock_ctor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(lf, "_ChatOpenAI", mock_ctor)

    out = wf._get_workflow_llm()
    assert out is mock_ctor.return_value
    mock_ctor.assert_called_once()
    kwargs = mock_ctor.call_args.kwargs
    assert kwargs["model"] == "gpt-5.1"
    assert kwargs["openai_api_base"] == "http://litellm.test:4000/v1"
    assert kwargs["openai_api_key"] == "sk-litellm-test"
