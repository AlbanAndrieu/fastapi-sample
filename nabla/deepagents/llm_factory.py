"""Build LangChain chat models: LiteLLM proxy first, then Azure OpenAI, then direct OpenAI."""

from __future__ import annotations

import os
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from nabla import config_settings as _config_settings
from nabla.config_settings import AzureOpenAiInstance, get_settings

DEFAULT_CHAT_MODEL = _config_settings.DEFAULT_CHAT_MODEL

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
    return raw or get_settings().default_chat_model


def resolve_openai_api_key_and_model(
    *, model_name: str | None = None,
) -> tuple[str, str]:
    """
    API key and chat model string for the legacy OpenAI Python SDK.

    Uses the same LiteLLM → Azure → direct OpenAI routing as :func:`build_chat_llm`.
    Azure returns the deployment-facing model name from settings (first entry if comma-separated).
    """
    settings = get_settings()
    litellm_url = (settings.litellm_url or "").strip()
    resolved = model_name or settings.default_chat_model
    if litellm_url:
        return settings.litellm_api_key.get_secret_value(), resolved
    if settings.azure_openai_instance:
        instance: AzureOpenAiInstance = next(iter(settings.azure_openai_instance.values()))
        return instance.api_key, _azure_chat_model_name(instance)
    return os.environ["OPENAI_API_KEY"], resolved


def build_chat_llm(*, model_name: str | None = None) -> BaseChatModel:
    """
    Prefer LiteLLM (``LITELLM_URL``), then configured Azure OpenAI, then ``OPENAI_API_KEY``.
    """
    settings = get_settings()
    resolved_model = model_name if model_name is not None else settings.default_chat_model
    litellm_url = (settings.litellm_url or "").strip()
    if litellm_url:
        return _ChatOpenAI(
            model=resolved_model,
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

    return _ChatOpenAI(model=resolved_model)
