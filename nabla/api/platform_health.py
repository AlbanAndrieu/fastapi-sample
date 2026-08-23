"""Optional platform and observability health probes."""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

import httpx

from nabla.api.cloudflare_tunnels import CloudflareTunnelSettings

_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
_LOGFIRE_DEFAULT_BASE_URL = "https://logfire-api.pydantic.dev"
_PFSENSE_STATUS_PATH = "/api/v2/status/system"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
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
    """Verify configured Logfire ingestion DNS/TCP/TLS connectivity without emitting telemetry."""
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


async def check_cloudflare_tunnels() -> dict[str, Any]:
    """Check Cloudflare Tunnel control-plane and tunnel health read-only."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are not configured",
            "probe": "cloudflare_tunnel_api",
        }

    url = f"{_CLOUDFLARE_API_BASE}/accounts/{settings.account_id}/cfd_tunnel"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.api_token}",
                    "Accept": "application/json",
                },
                params={"is_deleted": "false"},
            )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return {
            "reachable": False,
            "api_reachable": False,
            "error": _short_error(exc),
            "probe": "cloudflare_tunnel_api",
        }

    tunnels = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(tunnels, list):
        return {
            "reachable": False,
            "api_reachable": True,
            "error": "Cloudflare Tunnel API returned an unexpected payload",
            "probe": "cloudflare_tunnel_api",
        }

    statuses = [
        str(tunnel.get("status") or "unknown").lower()
        for tunnel in tunnels
        if isinstance(tunnel, dict)
    ]
    unhealthy = [
        status for status in statuses if status in {"inactive", "degraded", "down"}
    ]
    healthy = sum(status == "healthy" for status in statuses)
    return {
        "reachable": not unhealthy,
        "api_reachable": True,
        "http_status": response.status_code,
        "probe": "cloudflare_tunnel_api",
        "tunnel_count": len(statuses),
        "healthy_tunnels": healthy,
        "unhealthy_tunnels": len(unhealthy),
        "tunnel_statuses": statuses,
        "degraded": bool(unhealthy),
    }


async def check_pfsense_api() -> dict[str, Any]:
    """Check the configured pfSense REST API v2 status endpoint read-only."""
    base_url = os.getenv("PFSENSE_API_URL", "").strip().rstrip("/")
    api_key = os.getenv("PFSENSE_API_KEY", "").strip()
    if not base_url or not api_key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "PFSENSE_API_URL and PFSENSE_API_KEY are not configured",
            "probe": "pfsense_rest_api_v2",
        }
    if not base_url.lower().startswith("https://"):
        return {
            "reachable": False,
            "error": "PFSENSE_API_URL must use HTTPS when API-key authentication is enabled",
            "probe": "pfsense_rest_api_v2",
        }

    verify_ssl = (
        os.getenv("PFSENSE_API_VERIFY_SSL", "true").strip().lower() in _TRUE_VALUES
    )
    url = f"{base_url}{_PFSENSE_STATUS_PATH}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=verify_ssl,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                headers={"X-API-Key": api_key, "Accept": "application/json"},
            )
    except (httpx.HTTPError, OSError) as exc:
        return {
            "reachable": False,
            "error": _short_error(exc),
            "probe": "pfsense_rest_api_v2",
            "url": url,
        }

    healthy = 200 <= response.status_code < 400
    result: dict[str, Any] = {
        "reachable": healthy,
        "http_status": response.status_code,
        "probe": "pfsense_rest_api_v2",
        "url": url,
        "tls_trusted": True
        if verify_ssl and url.lower().startswith("https://")
        else None,
    }
    if not healthy:
        result["error"] = f"pfSense API returned HTTP {response.status_code}"
    return result


async def enrich_optional_platform_checks(payload: dict[str, Any]) -> dict[str, Any]:
    """Add optional platform/observability checks without changing required health semantics."""
    cloudflare, pfsense, logfire = await asyncio.gather(
        check_cloudflare_tunnels(),
        check_pfsense_api(),
        asyncio.to_thread(check_logfire_connectivity),
    )
    checks = dict(payload.get("checks") or {})
    checks["cloudflare"] = cloudflare
    checks["pfsense"] = pfsense
    checks["logfire"] = logfire
    return {**payload, "checks": checks}
