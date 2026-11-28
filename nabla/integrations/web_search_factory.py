"""Pick a configured web search backend (SearXNG → Tavily) and run queries.

SearXNG (TrueNAS LAN, ``SEARXNG_URL``) replaced Brave and Google on 28/11; Tavily
stays for FastAPI Cloud. Used by profile tools that need live snippets instead of
direct HTTP fetches.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from nabla.integrations import searxng_search, tavily_search
from nabla.config_settings import get_settings


class WebSearchProvider(str, Enum):
    SEARXNG = "searxng"
    TAVILY = "tavily"


def resolve_web_search_provider() -> WebSearchProvider | None:
    """Return the first usable provider: SearXNG (free, homelab), then Tavily."""
    if searxng_search.is_searxng_configured():
        return WebSearchProvider.SEARXNG
    if tavily_search.is_tavily_api_configured():
        return WebSearchProvider.TAVILY
    return None


def _format_results(data: dict[str, Any], *, max_chars: int) -> str:
    parts: list[str] = []
    for item in data.get("results") or []:
        title = item.get("title") or ""
        url = item.get("url") or ""
        content = item.get("content") or ""
        parts.append(f"Title: {title}\nURL: {url}\n{content}\n")
    out = "\n---\n".join(parts).strip()
    return out[:max_chars] if out else ""


def web_search_to_context_string(
    query: str,
    *,
    max_chars: int = 14_000,
    max_results: int | None = None,
) -> str:
    """Run web search with the first configured provider and return plain-text context."""
    provider = resolve_web_search_provider()
    if provider is None:
        msg = "No web search is configured. Set SEARXNG_URL (homelab) or TAVILY_API_KEY."
        raise RuntimeError(msg)
    if max_results is None:
        max_results = get_settings().web_search_max_results
    if provider is WebSearchProvider.SEARXNG:
        raw = searxng_search.web_search(query, max_results=max_results)
    else:
        raw = tavily_search.web_search(query, max_results=max_results)
    return _format_results(raw, max_chars=max_chars)
