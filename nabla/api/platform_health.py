"""Optional platform health probes for Cloudflare Tunnel and pfSense."""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import time
from typing import Any

import httpx

from nabla.api.cloudflare_tunnels import CloudflareTunnelSettings

_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
_PFSENSE_LIVENESS_PATH = "/api/v2/system/version"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PFSENSE_CONNECT_TIMEOUT_SEC = 3.0
_PFSENSE_READ_TIMEOUT_SEC = 5.0
logger = logging.getLogger(__name__)


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _http_error_kind(exc: BaseException) -> str:
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


def _pfsense_failure_stage(error_kind: str) -> str:
    if error_kind in {"connect_timeout", "connect_error", "tls_error", "os_error"}:
        return "connect"
    if error_kind == "pool_timeout":
        return "client_pool"
    if error_kind == "read_timeout":
        return "response"
    return "request"


def _cloudflare_api_error(response: httpx.Response) -> dict[str, Any]:
    """Return safe Cloudflare error details without exposing credentials or account IDs."""
    result: dict[str, Any] = {
        "reachable": False,
        "api_reachable": True,
        "http_status": response.status_code,
        "probe": "cloudflare_tunnel_api",
    }

    message = f"Cloudflare Tunnel API returned HTTP {response.status_code}"
    error_code: int | str | None = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
            cloudflare_message = str(first.get("message") or "").strip()
            if cloudflare_message:
                message = cloudflare_message[:240]
            error_code = first.get("code")

    if response.status_code == 404:
        message = (
            f"{message}; verify CLOUDFLARE_ACCOUNT_ID is the Cloudflare Account ID "
            "(not a Zone ID) and that CLOUDFLARE_API_TOKEN is scoped to that account"
        )

    result["error"] = message[:480]
    if error_code is not None:
        result["cloudflare_error_code"] = error_code
    return result


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
    except (httpx.HTTPError, OSError) as exc:
        return {
            "reachable": False,
            "api_reachable": False,
            "error": _short_error(exc),
            "probe": "cloudflare_tunnel_api",
        }

    if response.status_code >= 400:
        return _cloudflare_api_error(response)

    try:
        payload = response.json()
    except ValueError as exc:
        return {
            "reachable": False,
            "api_reachable": True,
            "http_status": response.status_code,
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
    """Check pfSense REST API liveness with the cheap read-only version endpoint."""
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
    url = f"{base_url}{_PFSENSE_LIVENESS_PATH}"
    timeout = httpx.Timeout(
        connect=_PFSENSE_CONNECT_TIMEOUT_SEC,
        read=_PFSENSE_READ_TIMEOUT_SEC,
        write=_PFSENSE_CONNECT_TIMEOUT_SEC,
        pool=_PFSENSE_CONNECT_TIMEOUT_SEC,
    )
    started = time.monotonic()
    logger.info(
        "pfSense API liveness probe started url=%s verify_ssl=%s connect_timeout_s=%s read_timeout_s=%s",
        url,
        verify_ssl,
        _PFSENSE_CONNECT_TIMEOUT_SEC,
        _PFSENSE_READ_TIMEOUT_SEC,
    )
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=verify_ssl,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                headers={"X-API-Key": api_key, "Accept": "application/json"},
            )
    except (httpx.HTTPError, OSError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        error_kind = _http_error_kind(exc)
        failure_stage = _pfsense_failure_stage(error_kind)
        exception_type = type(exc).__name__
        error = _short_error(exc)
        if error_kind == "read_timeout":
            error = (
                "pfSense accepted the connection but did not return the REST API "
                f"response within {_PFSENSE_READ_TIMEOUT_SEC:.0f}s"
            )
        logger.warning(
            "pfSense API liveness probe failed url=%s verify_ssl=%s error_kind=%s "
            "failure_stage=%s exception_type=%s elapsed_ms=%s error=%s",
            url,
            verify_ssl,
            error_kind,
            failure_stage,
            exception_type,
            elapsed_ms,
            error,
        )
        return {
            "reachable": False,
            "error": error,
            "error_kind": error_kind,
            "failure_stage": failure_stage,
            "exception_type": exception_type,
            "elapsed_ms": elapsed_ms,
            "probe": "pfsense_rest_api_v2",
            "path": _PFSENSE_LIVENESS_PATH,
            "url": url,
            "verify_ssl": verify_ssl,
        }

    elapsed_ms = round((time.monotonic() - started) * 1000)
    healthy = 200 <= response.status_code < 400
    logger.info(
        "pfSense API liveness probe completed url=%s verify_ssl=%s http_status=%s "
        "elapsed_ms=%s reachable=%s",
        url,
        verify_ssl,
        response.status_code,
        elapsed_ms,
        healthy,
    )
    result: dict[str, Any] = {
        "reachable": healthy,
        "http_status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "probe": "pfsense_rest_api_v2",
        "path": _PFSENSE_LIVENESS_PATH,
        "url": url,
        "verify_ssl": verify_ssl,
        "tls_trusted": True
        if verify_ssl and url.lower().startswith("https://")
        else None,
    }
    if not healthy:
        result["error"] = f"pfSense API returned HTTP {response.status_code}"
    return result


async def enrich_optional_platform_checks(payload: dict[str, Any]) -> dict[str, Any]:
    """Add optional platform checks without changing required health semantics."""
    cloudflare, pfsense = await asyncio.gather(
        check_cloudflare_tunnels(),
        check_pfsense_api(),
    )
    checks = dict(payload.get("checks") or {})
    checks["cloudflare"] = cloudflare
    checks["pfsense"] = pfsense
    return {**payload, "checks": checks}
