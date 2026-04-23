"""Tests for LiteLLM vs Azure vs direct OpenAI chat factory."""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from nabla.ai import llm_factory as lf
from nabla.config_settings import AzureOpenAiInstance


def test_litellm_openai_api_base_appends_v1() -> None:
    assert lf.litellm_openai_api_base("http://172.17.0.57:4100") == "http://172.17.0.57:4100/v1"


def test_litellm_openai_api_base_preserves_existing_v1() -> None:
    assert lf.litellm_openai_api_base("http://host:1/v1") == "http://host:1/v1"


def test_build_chat_llm_uses_litellm_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="http://proxy:4000",
        litellm_api_key=SecretStr("sk-test"),
        azure_openai_instance={},
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    llm = lf.build_chat_llm(model_name="gpt-5.1")
    assert llm.openai_api_base == "http://proxy:4000/v1"
    key = llm.openai_api_key
    resolved = key.get_secret_value() if hasattr(key, "get_secret_value") else key
    assert resolved == "sk-test"


def test_build_chat_llm_falls_back_to_azure_when_no_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = AzureOpenAiInstance(
        url="https://jmllm-test.openai.azure.com",
        api_key="azure-key",
        api_alias="my-deployment",
        available_models="gpt-4o-global,gpt-4o",
    )
    fake = SimpleNamespace(
        litellm_url="",
        litellm_api_key=SecretStr(""),
        azure_openai_instance={"a": instance},
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    llm = lf.build_chat_llm()
    assert llm.azure_endpoint == "https://jmllm-test.openai.azure.com"
    assert llm.deployment_name == "my-deployment"


def test_build_chat_llm_falls_back_to_openai_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="",
        litellm_api_key=SecretStr(""),
        azure_openai_instance={},
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-direct")
    llm = lf.build_chat_llm(model_name="gpt-4o-mini")
    assert llm.model_name == "gpt-4o-mini"
