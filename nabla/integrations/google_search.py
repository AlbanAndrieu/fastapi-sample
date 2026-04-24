"""Google Custom Search JSON API using ``GOOGLE_SEARCH_API_KEY`` and a search engine id (cx)."""

from __future__ import annotations

from typing import Any

import httpx

from nabla.integrations.env_secrets import google_search_credentials_runtime

_GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def _google_cse_credentials() -> tuple[str | None, str | None]:
    return google_search_credentials_runtime()


def is_google_programmable_search_configured() -> bool:
    """Return True when API key and Programmable Search engine id (cx) are both set."""
    key, cx = _google_cse_credentials()
    return key is not None and cx is not None


def web_search(
    query: str,
    *,
    num: int = 10,
) -> dict[str, Any]:
    """Call Google Custom Search JSON API and return the JSON body.

    Requires ``GOOGLE_SEARCH_API_KEY`` and a Programmable Search Engine id
    (``GOOGLE_SEARCH_CX``, or ``GOOGLE_CSE_ID``, or ``GOOGLE_SEARCH_ENGINE_ID``).

    Args:
        query: Search query.
        num: Number of results (API maximum is typically 10 per request).

    Returns:
        Parsed JSON response from Google.

    Raises:
        RuntimeError: If credentials or search engine id are missing.
    """
    key, cx = _google_cse_credentials()
    if key is None:
        msg = "GOOGLE_SEARCH_API_KEY is not set or empty; configure it in the environment."
        raise RuntimeError(msg)
    if cx is None:
        msg = "Google Custom Search requires a search engine id (cx). Set GOOGLE_SEARCH_CX (or GOOGLE_CSE_ID / GOOGLE_SEARCH_ENGINE_ID)."
        raise RuntimeError(msg)

    capped = min(max(num, 1), 10)
    params: dict[str, str | int] = {
        "key": key,
        "cx": cx,
        "q": query,
        "num": capped,
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.get(_GOOGLE_CSE_URL, params=params)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data
