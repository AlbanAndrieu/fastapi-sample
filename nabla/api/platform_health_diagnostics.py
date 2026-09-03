"""Sanitized transport diagnostics shared by optional platform probes."""

from __future__ import annotations

from datetime import UTC, datetime
import ssl

import httpx


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp for successful observations."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def short_error(exc: BaseException) -> str:
    """Bound external transport errors before exposing them in health payloads."""
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def http_error_kind(exc: BaseException) -> str:
    """Classify transport failures for safe runtime diagnostics."""
    message = str(exc).casefold()
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        if any(marker in message for marker in ("certificate", "ssl", "tls")):
            return "tls_error"
        return "connect_error"
    if isinstance(exc, ssl.SSLError) or any(
        marker in message for marker in ("certificate", "ssl", "tls")
    ):
        return "tls_error"
    if isinstance(exc, httpx.HTTPError):
        return "http_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "unknown_error"


def pfsense_failure_stage(error_kind: str) -> str:
    """Map a sanitized transport class to the pfSense diagnostic stage."""
    if error_kind in {"connect_timeout", "connect_error", "tls_error", "os_error"}:
        return "connect"
    if error_kind == "pool_timeout":
        return "client_pool"
    if error_kind == "read_timeout":
        return "response"
    return "request"
