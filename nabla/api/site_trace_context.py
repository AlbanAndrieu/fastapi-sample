"""Validated W3C trace context for authenticated Site health requests."""

from __future__ import annotations

import re

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-(?:00|01)$")


def extract_site_trace_id(value: str | None) -> str | None:
    """Return a safe trace ID; reject malformed values and all-zero identifiers."""
    if not isinstance(value, str):
        return None
    match = _TRACEPARENT.fullmatch(value)
    if match is None or set(match.group(1)) == {"0"} or set(match.group(2)) == {"0"}:
        return None
    return match.group(1)
