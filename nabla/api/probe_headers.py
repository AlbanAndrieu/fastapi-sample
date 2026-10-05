"""Low-cardinality provenance and W3C trace context for outbound probes."""

from __future__ import annotations

import os
import secrets

from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

_ALLOWED_PROBES = frozenset(
    {
        "pfsense-posture",
        "pfsense-security",
        "pfsense-posture-auth-smoke",
        "pfsense-security-auth-smoke",
        "unknown",
    },
)
_ALLOWED_SOURCES = frozenset({"fastapi-cloud", "truenas", "workstation", "unknown"})


def _probe_name(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in _ALLOWED_PROBES else "unknown"


def _probe_source(*, default: str = "unknown") -> str:
    """Resolve a bounded probe source without trusting arbitrary header input."""
    configured = os.getenv("NABLA_PROBE_SOURCE", "").strip().lower()
    if configured in _ALLOWED_SOURCES:
        return configured
    if os.getenv("FASTAPI_RUNTIME_MODE", "").strip().lower() == "homelab":
        return "truenas"
    return default if default in _ALLOWED_SOURCES else "unknown"


def _nonzero_hex(byte_length: int) -> str:
    while True:
        value = secrets.token_hex(byte_length)
        if any(char != "0" for char in value):
            return value


def new_traceparent() -> str:
    """Return a valid unsampled W3C Trace Context root identifier."""
    trace_id = _nonzero_hex(16)
    parent_id = _nonzero_hex(8)
    return f"00-{trace_id}-{parent_id}-00"


def _trace_headers() -> dict[str, str]:
    """Propagate active OTel trace context, with a standalone fallback."""
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    if "traceparent" not in carrier:
        carrier["traceparent"] = new_traceparent()
    return {
        key: value
        for key, value in carrier.items()
        if key in {"traceparent", "tracestate"}
    }


def probe_headers(
    probe: str,
    *,
    default_source: str = "unknown",
) -> dict[str, str]:
    """Build non-authentication metadata for an outbound diagnostic request."""
    return {
        "Nabla-Probe": _probe_name(probe),
        "Nabla-Probe-Source": _probe_source(default=default_source),
        **_trace_headers(),
    }
