"""Contracts for outbound diagnostic probe provenance headers."""

import re

from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
    use_span,
)

from nabla.api import probe_headers


_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-00$")


def test_probe_headers_use_bounded_custom_fields_and_w3c_traceparent(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NABLA_PROBE_SOURCE", "fastapi-cloud")

    headers = probe_headers.probe_headers("pfsense-posture")

    assert headers["Nabla-Probe"] == "pfsense-posture"
    assert headers["Nabla-Probe-Source"] == "fastapi-cloud"
    assert _TRACEPARENT.fullmatch(headers["traceparent"])
    assert not any(name.lower().startswith("x-nabla") for name in headers)

    next_headers = probe_headers.probe_headers("pfsense-posture")
    assert next_headers["traceparent"] != headers["traceparent"]


def test_homelab_runtime_is_attributed_to_truenas(monkeypatch) -> None:
    monkeypatch.delenv("NABLA_PROBE_SOURCE", raising=False)
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")

    headers = probe_headers.probe_headers("pfsense-security")

    assert headers["Nabla-Probe-Source"] == "truenas"


def test_invalid_configured_source_fails_closed_to_default(monkeypatch) -> None:
    monkeypatch.setenv("NABLA_PROBE_SOURCE", "bad\r\ninjected: value")

    headers = probe_headers.probe_headers(
        "pfsense-auth-smoke",
        default_source="workstation",
    )

    assert headers["Nabla-Probe-Source"] == "workstation"


def test_probe_headers_propagate_active_otel_context(monkeypatch) -> None:
    monkeypatch.setenv("NABLA_PROBE_SOURCE", "truenas")
    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )

    with use_span(NonRecordingSpan(span_context), end_on_exit=False):
        headers = probe_headers.probe_headers("pfsense-posture")

    assert headers["traceparent"] == (
        "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    )
