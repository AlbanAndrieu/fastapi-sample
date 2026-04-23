"""Build LangChain chat models: LiteLLM proxy first, then Azure OpenAI, then direct OpenAI."""

from __future__ import annotations

import os
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from nabla.config_settings import AzureOpenAiInstance, get_settings

_ChatOpenAI = cast(Any, ChatOpenAI)
_AzureChatOpenAI = cast(Any, AzureChatOpenAI)


def litellm_openai_api_base(url: str) -> str:
    """Normalize proxy host to the OpenAI client ``api_base`` (…/v1)."""
    base = url.strip().rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def _azure_chat_model_name(instance: AzureOpenAiInstance) -> str:
    raw = (instance.available_models or "").strip()
    if "," in raw:
        return raw.split(",", maxsplit=1)[0].strip()
    return raw or "gpt-5.1"


def build_chat_llm(*, model_name: str = "gpt-5.1") -> BaseChatModel:
    """
    Prefer LiteLLM (``LITELLM_URL``), then configured Azure OpenAI, then ``OPENAI_API_KEY``.
    """
    settings = get_settings()
    litellm_url = (settings.litellm_url or "").strip()
    if litellm_url:
        return _ChatOpenAI(
            model=model_name,
            openai_api_base=litellm_openai_api_base(litellm_url),
            openai_api_key=settings.litellm_api_key.get_secret_value(),
        )

    if settings.azure_openai_instance:
        instance: AzureOpenAiInstance = next(iter(settings.azure_openai_instance.values()))
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        return _AzureChatOpenAI(
            azure_endpoint=instance.url,
            deployment_name=instance.api_alias,
            openai_api_version=api_version,
            api_key=instance.api_key,
            model=_azure_chat_model_name(instance),
        )

    return _ChatOpenAI(model=model_name)
