"""Tests for LiteLLM vs Azure vs direct OpenAI chat factory."""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from nabla.deepagents import llm_factory as lf
from nabla.config_settings import DEFAULT_CHAT_MODEL, AzureOpenAiInstance


def test_litellm_openai_api_base_appends_v1() -> None:
    assert lf.litellm_openai_api_base("http://172.17.0.57:4100") == "http://172.17.0.57:4100/v1"


def test_litellm_openai_api_base_preserves_existing_v1() -> None:
    assert lf.litellm_openai_api_base("http://host:1/v1") == "http://host:1/v1"


def test_build_chat_llm_uses_litellm_when_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="http://proxy:4000",
        litellm_api_key=SecretStr("sk-test"),
        azure_openai_instance={},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    llm = lf.build_chat_llm(model_name=DEFAULT_CHAT_MODEL)
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
        default_chat_model=DEFAULT_CHAT_MODEL,
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
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-direct")
    llm = lf.build_chat_llm(model_name="gpt-4o-mini")
    assert llm.model_name == "gpt-4o-mini"


def test_resolve_openai_api_key_and_model_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="http://proxy:4000",
        litellm_api_key=SecretStr("sk-litellm"),
        azure_openai_instance={},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    key, model = lf.resolve_openai_api_key_and_model()
    assert key == "sk-litellm"
    assert model == lf.DEFAULT_CHAT_MODEL


def test_resolve_openai_api_key_and_model_azure_first_model(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = AzureOpenAiInstance(
        url="https://x.openai.azure.com",
        api_key="azure-k",
        api_alias="dep",
        available_models="gpt-4o-global,gpt-4o",
    )
    fake = SimpleNamespace(
        litellm_url="",
        litellm_api_key=SecretStr(""),
        azure_openai_instance={"a": instance},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    key, model = lf.resolve_openai_api_key_and_model()
    assert key == "azure-k"
    assert model == "gpt-4o-global"


def test_resolve_openai_api_key_and_model_direct_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        litellm_url="",
        litellm_api_key=SecretStr(""),
        azure_openai_instance={},
        default_chat_model=DEFAULT_CHAT_MODEL,
    )
    monkeypatch.setattr(lf, "get_settings", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    key, model = lf.resolve_openai_api_key_and_model(model_name="gpt-4o-mini")
    assert key == "sk-env"
    assert model == "gpt-4o-mini"
