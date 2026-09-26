"""Optional observability health probes."""

from __future__ import annotations

import asyncio
import socket
import ssl
from typing import Any

from pydantic import ValidationError

from nabla.settings.observability import LogfireProbeSettings


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def check_logfire_connectivity() -> dict[str, Any]:
    """Verify Logfire ingestion DNS/TCP/TLS connectivity without emitting telemetry."""
    try:
        settings = LogfireProbeSettings()
    except ValidationError:
        return {
            "reachable": False,
            "error": "LOGFIRE_BASE_URL must be a valid HTTPS URL",
            "probe": "ingest_tls_socket",
        }

    if not settings.probe_enabled:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "Logfire is disabled or not configured",
            "probe": "ingest_tls_socket",
        }

    if not settings.token:
        return {
            "reachable": False,
            "error": "Logfire is enabled but LOGFIRE_TOKEN is not configured",
            "probe": "ingest_tls_socket",
        }

    host = settings.probe_host
    port = settings.probe_port
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


async def enrich_optional_observability_checks(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Add optional observability checks without changing required health semantics."""
    logfire = await asyncio.to_thread(check_logfire_connectivity)
    checks = dict(payload.get("checks") or {})
    checks["logfire"] = logfire
    return {**payload, "checks": checks}
