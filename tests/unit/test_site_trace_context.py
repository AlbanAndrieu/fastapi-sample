"""W3C traceparent validation without external services."""

from nabla.api.site_trace_context import extract_site_trace_id


def test_valid_site_traceparent() -> None:
    trace_id = "a" * 32
    assert extract_site_trace_id(f"00-{trace_id}-{'b' * 16}-01") == trace_id
    assert extract_site_trace_id(f"00-{trace_id}-{'b' * 16}-00") == trace_id


def test_no_header_injection_or_invalid_trace_ids() -> None:
    for value in (None, "", "not-a-trace", "00-" + "0" * 32 + "-" + "b" * 16 + "-01",
                  "00-" + "a" * 32 + "-" + "0" * 16 + "-01",
                  "00-" + "a" * 32 + "-" + "b" * 16 + "-ff",
                  "00-" + "a" * 32 + "-" + "b" * 16 + "-01\r\nX-Diagnostics-Key: secret"):
        assert extract_site_trace_id(value) is None
