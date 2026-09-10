"""Sanitized HTTP probe error classification shared by health orchestration."""

from __future__ import annotations

import httpx


def http_probe_error_kind(exc: Exception) -> str:
    """Classify outbound HTTP failures without exposing implementation details."""
    message = str(exc).lower()
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if any(marker in message for marker in ("certificate", "ssl", "tls")):
        return "tls_error"
    if any(
        marker in message
        for marker in (
            "name or service not known",
            "nodename nor servname",
            "temporary failure in name resolution",
            "getaddrinfo",
        )
    ):
        return "dns_error"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.HTTPError):
        return "http_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "unknown_error"
