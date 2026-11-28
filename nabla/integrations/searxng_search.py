"""SearXNG web search, the TrueNAS LAN App that replaced Brave and Google (28/11).

``SEARXNG_URL`` (for example ``http://172.17.0.24:30053``) is only reachable
from the homelab: FastAPI Cloud keeps Tavily.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from nabla.config_settings import get_settings


def _searxng_url() -> str:
    return os.getenv("SEARXNG_URL", "").strip().rstrip("/")


def is_searxng_configured() -> bool:
    """Return True when ``SEARXNG_URL`` is set."""
    return bool(_searxng_url())


def web_search(query: str, *, max_results: int | None = None) -> dict[str, Any]:
    """Query the SearXNG JSON API and keep the first results' title, URL and snippet.

    Raises:
        RuntimeError: If ``SEARXNG_URL`` is not configured.
    """
    base = _searxng_url()
    if not base:
        msg = "SEARXNG_URL is not set; SearXNG is a TrueNAS LAN App (FastAPI Cloud uses Tavily)."
        raise RuntimeError(msg)
    resolved = get_settings().web_search_max_results if max_results is None else max_results
    capped = min(max(int(resolved), 1), 5)
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{base}/search", params={"q": query, "format": "json"})
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    results = [{key: item.get(key) or "" for key in ("title", "url", "content", "engine")} for item in (data.get("results") or [])[:capped]]
    return {"query": query, "results": results, "unresponsive_engines": data.get("unresponsive_engines") or []}
