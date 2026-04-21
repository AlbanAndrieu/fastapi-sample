"""Brave Web Search using ``BRAVE_API_KEY`` from settings."""

from __future__ import annotations

from typing import Any

import httpx

from nabla.config_settings import get_settings
from nabla.integrations.env_secrets import secret_from_env_or_settings

_BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def _brave_api_key() -> str | None:
    settings = get_settings()
    return secret_from_env_or_settings(
        "BRAVE_API_KEY",
        settings_secret=settings.brave_api_key,
    )


def brave_web_search(
    query: str,
    *,
    count: int = 10,
) -> dict[str, Any]:
    """Call Brave Web Search and return the JSON body.

    Args:
        query: Search query.
        count: Number of results (provider may cap this).

    Returns:
        Parsed JSON response from Brave.

    Raises:
        RuntimeError: If ``BRAVE_API_KEY`` is not configured.
    """
    key = _brave_api_key()
    if key is None:
        msg = "BRAVE_API_KEY is not set or empty; configure it in the environment."
        raise RuntimeError(msg)

    params: dict[str, str | int] = {"q": query, "count": count}
    headers = {
        "X-Subscription-Token": key,
        "Accept": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.get(_BRAVE_WEB_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data
