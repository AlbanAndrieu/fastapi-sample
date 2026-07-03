"""Resolve managed prompts from Langfuse with in-repo string fallbacks."""

from __future__ import annotations

import os
from functools import lru_cache

from langfuse import Langfuse

from nabla.utils.logger import logger

_DEFAULT_AGENT_SYSTEM_PROMPT_NAME = "nabla-agent-system"


def _langfuse_credentials_configured() -> bool:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    return bool(pk and sk)


@lru_cache(maxsize=1)
def _langfuse_client() -> Langfuse:
    host = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").strip().rstrip("/")
    if not host:
        host = "https://cloud.langfuse.com"
    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"].strip(),
        secret_key=os.environ["LANGFUSE_SECRET_KEY"].strip(),
        host=host,
    )


def clear_langfuse_client_cache() -> None:
    """Clear cached Langfuse client (e.g. after tests change ``os.environ``)."""
    _langfuse_client.cache_clear()


def resolve_langfuse_text_prompt(
    name: str,
    *,
    fallback: str,
    label: str | None = None,
) -> str:
    """Fetch a text prompt from Langfuse, or return ``fallback`` if unavailable or fetch fails."""
    if not _langfuse_credentials_configured():
        return fallback
    try:
        client = _langfuse_client()
    except Exception as exc:
        logger.warning("Langfuse client init failed: %s; using local fallback prompt", exc)
        return fallback
    try:
        prompt_client = client.get_prompt(
            name,
            type="text",
            label=label,
            fallback=fallback,
            max_retries=1,
        )
        return prompt_client.compile()
    except Exception as exc:
        logger.warning("Langfuse get_prompt(%r) failed: %s; using local fallback", name, exc)
        return fallback


def resolve_nabla_agent_system_prompt(fallback: str) -> str:
    """Load the nabla AI workflow system prompt from Langfuse when configured."""
    name = os.environ.get("LANGFUSE_AGENT_SYSTEM_PROMPT_NAME", _DEFAULT_AGENT_SYSTEM_PROMPT_NAME).strip() or _DEFAULT_AGENT_SYSTEM_PROMPT_NAME
    label_raw = os.environ.get("LANGFUSE_PROMPT_LABEL", "").strip()
    label = label_raw or None
    return resolve_langfuse_text_prompt(name, fallback=fallback, label=label)
