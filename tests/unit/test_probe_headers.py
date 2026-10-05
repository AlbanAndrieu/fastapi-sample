"""Contracts for passive outbound probe identification and trace propagation."""

from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from nabla.api.probe_headers import probe_request_headers


def _clear_runtime_markers(monkeypatch) -> None:
    for name in (
        "FASTAPI_CLOUD",
        "FASTAPI_CLOUD_APP_ID",
        "FASTAPI_ENV",
        "FASTAPI_RUNTIME_MODE",
        "SICKZ_NETWORK_LABEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_homelab_probe_headers_identify_truenas_without_baggage(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")

    headers = probe_request_headers("pfsense-posture")

    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == "fastapi-sample-health/1.0"
    assert headers["Nabla-Probe-Origin"] == "truenas"
    assert headers["Nabla-Probe-Name"] == "pfsense-posture"
    assert UUID(headers["Nabla-Probe-Request-ID"]).version == 4
    assert "X-API-Key" not in headers
    assert "baggage" not in headers


def test_cloud_probe_headers_identify_fastapi_cloud(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("FASTAPI_CLOUD_APP_ID", "app")

    headers = probe_request_headers("pfsense-security")

    assert headers["Nabla-Probe-Origin"] == "fastapi-cloud"


def test_local_probe_headers_identify_workstation(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("FASTAPI_ENV", "local")

    headers = probe_request_headers("pfsense-auth-posture")

    assert headers["Nabla-Probe-Origin"] == "workstation"


def test_trace_context_is_propagated_without_otel_baggage(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")
    context = SpanContext(
        trace_id=0x0123456789ABCDEF0123456789ABCDEF,
        span_id=0x0123456789ABCDEF,
        is_remote=False,
        trace_flags=TraceFlags.SAMPLED,
    )

    with trace.use_span(NonRecordingSpan(context), end_on_exit=False):
        headers = probe_request_headers("pfsense-posture")

    assert headers["traceparent"] == (
        "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    )
    assert "baggage" not in headers


def test_blank_probe_name_is_rejected() -> None:
    try:
        probe_request_headers("   ")
    except ValueError as exc:
        assert str(exc) == "probe_name must not be blank"
    else:
        raise AssertionError("blank probe name must fail closed")


def test_probe_request_id_is_unique_per_http_request(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("FASTAPI_RUNTIME_MODE", "homelab")

    first = probe_request_headers("pfsense-posture")
    second = probe_request_headers("pfsense-posture")

    assert first["Nabla-Probe-Request-ID"] != second["Nabla-Probe-Request-ID"]
    assert "X-API-Key" not in first
    assert "X-API-Key" not in second
