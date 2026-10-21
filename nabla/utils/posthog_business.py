"""Strict, disabled-by-default PostHog business event exporter.

No request payload, host, IP, token, or raw exception is accepted as telemetry.
The call is synchronous and intended for background jobs, not request handlers.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from urllib.request import Request, urlopen

_ALLOWED = {
    "catalog_loaded": frozenset({"app", "environment", "catalog_version", "status", "release"}),
    "catalog_load_failed": frozenset({"app", "environment", "catalog_version", "error_class", "release"}),
    "diagnostics_unlock_failed": frozenset({"app", "environment", "http_status", "error_class"}),
}
_ALLOWED_STATUS = frozenset({"OK", "WARN", "FAIL", "UNKNOWN"})
_ALLOWED_ENV = frozenset({"production", "preview", "development"})
_ALLOWED_ERRORS = frozenset({"unauthorized", "forbidden", "upstream", "timeout", "unavailable", "invalid_response"})
_ALLOWED_APPS = frozenset({"nabla-site-alban", "nabla-site-bababou", "fastapi-sample"})


def _validate(event: str, properties: Mapping[str, object]) -> dict[str, str | int] | None:
    allowed = _ALLOWED.get(event)
    if allowed is None or not set(properties).issubset(allowed):
        return None
    safe: dict[str, str | int] = {}
    for key, value in properties.items():
        if key == "http_status":
            if type(value) is not int or value not in {401, 403, 404, 429, 500, 502, 503, 504}:
                return None
            safe[key] = value
        elif not isinstance(value, str) or len(value) > 64:
            return None
        elif key == "app" and value not in _ALLOWED_APPS:
            return None
        elif key == "environment" and value not in _ALLOWED_ENV:
            return None
        elif key == "status" and value not in _ALLOWED_STATUS:
            return None
        elif key == "error_class" and value not in _ALLOWED_ERRORS:
            return None
        elif key in {"catalog_version", "release"} and not value.replace(".", "").replace("-", "").replace("_", "").isalnum():
            return None
        else:
            safe[key] = value
    return safe


def export_business_event(event: str, properties: Mapping[str, object]) -> bool:
    """Best-effort export. Never affects authorization or an API response."""
    if os.getenv("POSTHOG_BUSINESS_EVENTS_ENABLED", "false").lower() != "true":
        return False
    key = os.getenv("POSTHOG_PROJECT_KEY", "").strip()
    safe = _validate(event, properties)
    if not key or safe is None:
        return False
    # Fixed EU endpoint, never accept arbitrary destination URLs.
    payload = json.dumps({
        "api_key": key,
        "event": event,
        "distinct_id": "fastapi-sample-service",
        "properties": safe,
    }).encode("utf-8")
    try:
        request = Request(
            "https://eu.i.posthog.com/capture/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=1.0) as response:  # noqa: S310
            return 200 <= response.status < 300
    except (OSError, ValueError, TimeoutError):
        return False
