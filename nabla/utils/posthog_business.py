"""Strict, disabled-by-default PostHog business event exporter.

No request payload, host, IP, token, or raw exception is accepted as telemetry.
The call is synchronous and intended for background jobs, not request handlers.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

import httpx

_CAPTURE_URL = "https://eu.i.posthog.com/capture/"

_ALLOWED = {
    "catalog_loaded": frozenset({"app", "environment", "catalog_version", "status", "release"}),
    "catalog_load_failed": frozenset({"app", "environment", "catalog_version", "error_class", "release"}),
    "diagnostics_unlock_failed": frozenset({"app", "environment", "http_status", "error_class"}),
}
_ALLOWED_STATUS = frozenset({"OK", "WARN", "FAIL", "UNKNOWN"})
_ALLOWED_ENV = frozenset({"production", "preview", "development"})
_ALLOWED_ERRORS = frozenset({"unauthorized", "forbidden", "upstream", "timeout", "unavailable", "invalid_response"})
_ALLOWED_APPS = frozenset({"nabla-site-alban", "nabla-site-bababou", "fastapi-sample"})
_ALLOWED_HTTP_STATUS = frozenset({401, 403, 404, 429, 500, 502, 503, 504})
_ENUMERATED_VALUES = {
    "app": _ALLOWED_APPS,
    "environment": _ALLOWED_ENV,
    "status": _ALLOWED_STATUS,
    "error_class": _ALLOWED_ERRORS,
}
_VERSION_KEYS = frozenset({"catalog_version", "release"})
_SAFE_TOKEN = re.compile(r"[a-zA-Z0-9_.-]{1,64}")


def _safe_value(key: str, value: object) -> str | int | None:
    """Return the value only when it matches the key's allowlist, else None."""
    if key == "http_status":
        return value if type(value) is int and value in _ALLOWED_HTTP_STATUS else None
    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
        return None
    enumerated = _ENUMERATED_VALUES.get(key)
    if enumerated is not None and value not in enumerated:
        return None
    if key in _VERSION_KEYS and not value.replace(".", "").replace("-", "").replace("_", "").isalnum():
        return None
    return value


def _validate(event: str, properties: Mapping[str, object]) -> dict[str, str | int] | None:
    allowed = _ALLOWED.get(event)
    if allowed is None or not isinstance(properties, Mapping) or not set(properties).issubset(allowed):
        return None
    safe: dict[str, str | int] = {}
    for key, value in properties.items():
        checked = _safe_value(key, value)
        # One invalid property rejects the whole event (fail closed).
        if checked is None:
            return None
        safe[key] = checked
    return safe


def export_business_event(event: str, properties: Mapping[str, object]) -> bool:
    """Best-effort export. Never affects authorization or an API response."""
    if os.getenv("POSTHOG_BUSINESS_EVENTS_ENABLED", "false").lower() != "true":
        return False
    key = os.getenv("POSTHOG_PROJECT_KEY", "").strip()
    safe = _validate(event, properties)
    if not key or safe is None:
        return False
    payload = {
        "api_key": key,
        "event": event,
        "distinct_id": "fastapi-sample-service",
        "properties": safe,
    }
    try:
        # Fixed EU endpoint, never accept arbitrary destination URLs.
        response = httpx.post(_CAPTURE_URL, json=payload, timeout=1.0)
    except httpx.HTTPError:
        return False
    return response.is_success
