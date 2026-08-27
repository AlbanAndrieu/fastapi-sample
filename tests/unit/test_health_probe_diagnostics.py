"""Tests for outbound health probe failure classification."""

import httpx

from nabla.api.health_checks import _http_probe_error_kind


def test_classifies_connect_timeout() -> None:
    assert _http_probe_error_kind(httpx.ConnectTimeout("timed out")) == "connect_timeout"


def test_classifies_read_timeout() -> None:
    assert _http_probe_error_kind(httpx.ReadTimeout("timed out")) == "read_timeout"


def test_classifies_tls_error_before_connect_error() -> None:
    error = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    assert _http_probe_error_kind(error) == "tls_error"


def test_classifies_dns_error_before_connect_error() -> None:
    error = httpx.ConnectError("[Errno -2] Name or service not known")
    assert _http_probe_error_kind(error) == "dns_error"


def test_classifies_generic_connect_error() -> None:
    assert _http_probe_error_kind(httpx.ConnectError("connection refused")) == "connect_error"
