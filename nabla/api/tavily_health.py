"""Tavily key/availability probe used by ``/healthz``."""

from __future__ import annotations

from typing import Any

import httpx

from nabla.api.health_probe_utils import normalize_probe_error
from nabla.integrations.tavily_search import tavily_api_key

_TAVILY_USAGE_URL = "https://api.tavily.com/usage"


def probe_tavily_search() -> dict[str, Any]:
    """Validate the Tavily key with ``GET /usage`` instead of running a search.

    A search for ``"."`` is rejected by Tavily (``Query is invalid.``) and a
    real query would spend search credits on every cadenced probe.
    """
    api_key = tavily_api_key()
    if api_key is None:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "TAVILY_API_KEY not configured",
        }
    try:
        with httpx.Client(timeout=5.0) as http_client:
            response = http_client.get(
                _TAVILY_USAGE_URL,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            )
    except Exception as exc:
        return {"reachable": False, "error": normalize_probe_error(str(exc)), "probe": "usage"}
    result: dict[str, Any] = {"http_status": response.status_code, "probe": "usage"}
    if response.is_success:
        return {"reachable": True, **result}
    if response.status_code in {401, 403}:
        return {
            "reachable": False,
            "error": "Tavily rejected the configured API key",
            "failure_stage": "authentication",
            **result,
        }
    if response.status_code == 429:
        return {
            "reachable": None,
            "error": "Tavily rate limited the usage probe",
            "failure_stage": "rate_limited",
            **result,
        }
    return {"reachable": False, "error": f"http_status={response.status_code}", **result}
