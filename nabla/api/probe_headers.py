"""Non-authoritative metadata for outbound health and diagnostic probes."""

from __future__ import annotations

from uuid import uuid4

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from nabla.api.runtime_environment import runtime_mode

_PROBE_USER_AGENT = "fastapi-sample-health/1.0"
_ORIGIN_BY_RUNTIME_MODE = {
    "fastapi_cloud": "fastapi-cloud",
    "homelab": "truenas",
    "cloud_paas": "cloud-paas",
    "local": "workstation",
}


def probe_origin() -> str:
    """Return a low-cardinality diagnostic origin label for outbound probes."""
    return _ORIGIN_BY_RUNTIME_MODE.get(runtime_mode(), "unknown")


def probe_request_headers(probe_name: str) -> dict[str, str]:
    """Build passive probe metadata without changing auth or routing semantics."""
    normalized_name = probe_name.strip()
    if not normalized_name:
        raise ValueError("probe_name must not be blank")

    headers = {
        "Accept": "application/json",
        "User-Agent": _PROBE_USER_AGENT,
        "Nabla-Probe-Origin": probe_origin(),
        "Nabla-Probe-Name": normalized_name,
        "Nabla-Probe-Request-ID": str(uuid4()),
    }

    # Inject only W3C Trace Context. Do not use the global propagator here:
    # it may include W3C baggage, which can cross trust boundaries and carry
    # application-defined data unrelated to appliance health probes.
    trace_headers: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(trace_headers)
    for name in ("traceparent", "tracestate"):
        value = trace_headers.get(name)
        if value:
            headers[name] = value

    return headers
