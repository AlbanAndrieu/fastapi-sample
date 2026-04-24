"""Pick a configured web search backend (Google → Brave → Tavily) and run queries.

Google Programmable Search is tried first when ``GOOGLE_SEARCH_API_KEY`` and a cx id
are set; otherwise Brave, then Tavily. Used by profile tools that need live snippets
instead of direct HTTP fetches.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from nabla.integrations import brave_search, google_search, tavily_search


class WebSearchProvider(str, Enum):
    GOOGLE = "google"
    BRAVE = "brave"
    TAVILY = "tavily"


def resolve_web_search_provider() -> WebSearchProvider | None:
    """Return the first usable provider: Google (default preference), then Brave, Tavily."""
    if google_search.is_google_programmable_search_configured():
        return WebSearchProvider.GOOGLE
    if brave_search.is_brave_api_configured():
        return WebSearchProvider.BRAVE
    if tavily_search.is_tavily_api_configured():
        return WebSearchProvider.TAVILY
    return None


def _format_google_items(data: dict[str, Any], *, max_chars: int) -> str:
    parts: list[str] = []
    for item in data.get("items") or []:
        title = item.get("title") or ""
        link = item.get("link") or ""
        snippet = item.get("snippet") or ""
        parts.append(f"Title: {title}\nURL: {link}\n{snippet}\n")
    out = "\n---\n".join(parts).strip()
    return out[:max_chars] if out else ""


def _format_brave_web(data: dict[str, Any], *, max_chars: int) -> str:
    web = data.get("web") or {}
    results = web.get("results") or []
    parts: list[str] = []
    for item in results:
        title = item.get("title") or ""
        url = item.get("url") or ""
        desc = item.get("description") or ""
        parts.append(f"Title: {title}\nURL: {url}\n{desc}\n")
    out = "\n---\n".join(parts).strip()
    return out[:max_chars] if out else ""


def _format_tavily_results(data: dict[str, Any], *, max_chars: int) -> str:
    parts: list[str] = []
    for item in data.get("results") or []:
        title = item.get("title") or ""
        url = item.get("url") or ""
        content = item.get("content") or ""
        parts.append(f"Title: {title}\nURL: {url}\n{content}\n")
    out = "\n---\n".join(parts).strip()
    return out[:max_chars] if out else ""


def web_search_to_context_string(query: str, *, max_chars: int = 14_000) -> str:
    """Run web search with the first configured provider and return plain-text context."""
    provider = resolve_web_search_provider()
    if provider is None:
        msg = (
            "No web search API is configured. Set GOOGLE_SEARCH_API_KEY and a search "
            "engine id (GOOGLE_SEARCH_CX / GOOGLE_CSE_ID / GOOGLE_SEARCH_ENGINE_ID), "
            "or BRAVE_API_KEY, or TAVILY_API_KEY."
        )
        raise RuntimeError(msg)

    if provider is WebSearchProvider.GOOGLE:
        raw = google_search.web_search(query)
        return _format_google_items(raw, max_chars=max_chars)
    if provider is WebSearchProvider.BRAVE:
        raw = brave_search.web_search(query)
        return _format_brave_web(raw, max_chars=max_chars)
    raw = tavily_search.web_search(query)
    return _format_tavily_results(raw, max_chars=max_chars)
