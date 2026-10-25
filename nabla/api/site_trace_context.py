"""Strict W3C traceparent validation for machine-authenticated Site health calls."""
from __future__ import annotations
import re

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-(?:00|01)$")

def verified_site_trace_id(value: str | None) -> str | None:
    """Return bounded trace ID only; never reflect raw headers or baggage."""
    if not isinstance(value, str):
        return None
    match = _TRACEPARENT.fullmatch(value)
    if not match:
        return None
    trace_id, span_id = match.group(1), match.group(2)
    if set(trace_id) == {"0"} or set(span_id) == {"0"}:
        return None
    return trace_id
