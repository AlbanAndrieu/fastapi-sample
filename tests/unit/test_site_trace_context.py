from nabla.api.site_trace_context import extract_site_trace_id, verified_site_trace_id

def test_valid_w3c_site_trace_is_returned():
    assert verified_site_trace_id("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01") == "4bf92f3577b34da6a3ce929d0e0e4736"

def test_bad_or_injected_traces_never_pass():
    for value in (
        None, "", "bad", "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-ff",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01\r\nX-Key:bad",
    ):
        assert verified_site_trace_id(value) is None



def test_site_receipt_compatibility_and_sampling_flags():
    trace = "a" * 32
    assert extract_site_trace_id(f"00-{trace}-{'b' * 16}-00") == trace
    assert extract_site_trace_id(f"00-{trace}-{'b' * 16}-01") == trace
    assert extract_site_trace_id(f"00-{trace}-{'b' * 16}-ff") is None
    assert extract_site_trace_id("00-" + "0" * 32 + "-" + "b" * 16 + "-01") is None
