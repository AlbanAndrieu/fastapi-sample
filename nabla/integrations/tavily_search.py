"""Tavily web search using ``TAVILY_API_KEY`` from settings."""

from __future__ import annotations

from typing import Any, Literal

from tavily import TavilyClient

from nabla.config_settings import get_settings
from nabla.integrations.env_secrets import secret_from_env_or_settings

SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]


def get_tavily_client() -> TavilyClient | None:
    """Return a ``TavilyClient`` when ``TAVILY_API_KEY`` is set and non-empty."""
    settings = get_settings()
    key = secret_from_env_or_settings(
        "TAVILY_API_KEY",
        settings_secret=settings.tavily_api_key,
    )
    if key is None:
        return None
    return TavilyClient(api_key=key)


def tavily_search(
    query: str,
    *,
    search_depth: SearchDepth = "advanced",
) -> dict[str, Any]:
    """Run a Tavily search and return the API response dict.

    Args:
        query: Search query string.
        search_depth: Tavily search depth (default ``advanced``).

    Returns:
        Raw response mapping from ``TavilyClient.search``.

    Raises:
        RuntimeError: If the API key is not configured.
    """
    client = get_tavily_client()
    if client is None:
        msg = "TAVILY_API_KEY is not set or empty; configure it in the environment."
        raise RuntimeError(msg)
    return client.search(query=query, search_depth=search_depth)
