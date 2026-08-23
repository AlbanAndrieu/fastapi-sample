"""Optional observability health probes."""

from __future__ import annotations

import os
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

_LOGFIRE_DEFAULT_BASE_URL = "https://logfire-api.pydantic.dev"
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _logfire_enabled() -> bool:
    """Enable the probe only when configured or explicitly requested."""
    raw = os.getenv("LOGFIRE_ENABLED")
    if raw is None:
        raw = os.getenv("LOGFIRE_ENABLE")
    if raw is None:
        return bool(os.getenv("LOGFIRE_TOKEN", "").strip())
    return raw.strip().lower() not in _FALSE_VALUES


def check_logfire_connectivity() -> dict[str, Any]:
    """Verify Logfire ingestion DNS/TCP/TLS connectivity without emitting telemetry."""
    if not _logfire_enabled():
        return {
            "reachable": None,
            "skipped": True,
            "reason": "Logfire is disabled or not configured",
            "probe": "ingest_tls_socket",
        }

    token = os.getenv("LOGFIRE_TOKEN", "").strip()
    if not token:
        return {
            "reachable": False,
            "error": "Logfire is enabled but LOGFIRE_TOKEN is not configured",
            "probe": "ingest_tls_socket",
        }

    base_url = os.getenv("LOGFIRE_BASE_URL", _LOGFIRE_DEFAULT_BASE_URL).strip()
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return {
            "reachable": False,
            "error": "LOGFIRE_BASE_URL must be a valid HTTPS URL",
            "probe": "ingest_tls_socket",
        }

    host = parsed.hostname
    port = parsed.port or 443
    try:
        with socket.create_connection((host, port), timeout=3.0) as raw_socket:
            context = ssl.create_default_context()
            with context.wrap_socket(raw_socket, server_hostname=host):
                pass
    except (OSError, ssl.SSLError) as exc:
        return {
            "reachable": False,
            "error": _short_error(exc),
            "probe": "ingest_tls_socket",
            "host": host,
            "port": port,
        }

    return {
        "reachable": True,
        "probe": "ingest_tls_socket",
        "host": host,
        "port": port,
        "tls_trusted": True,
        "token_present": True,
    }
