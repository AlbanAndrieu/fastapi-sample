# ruff: noqa: PLW0603 -- cache state is intentionally process-local.
"""Optional platform health probes for Cloudflare Tunnel and pfSense."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
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
_PFSENSE_MAX_ATTEMPTS = 2
_PFSENSE_RETRY_DELAY_SEC = 0.2
_PFSENSE_CACHE_TTL_SEC = 30.0
_pfsense_cache_lock = asyncio.Lock()
_pfsense_cache: dict[str, Any] | None = None
_pfsense_cache_at = 0.0
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
    if isinstance(exc, ssl.SSLError) or any(marker in message for marker in ("certificate", "ssl", "tls")):
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


def _pfsense_posture_transport() -> tuple[str, str, bool, str]:
    """Resolve posture credentials, preferring the dedicated read-only identity."""
    posture_url = os.getenv("PFSENSE_POSTURE_API_URL", "").strip()
    posture_key = os.getenv("PFSENSE_POSTURE_API_KEY", "").strip()
    legacy_url = os.getenv("PFSENSE_API_URL", "").strip()
    legacy_key = os.getenv("PFSENSE_API_KEY", "").strip()

    dedicated = bool(posture_key)
    base_url = (posture_url or legacy_url).rstrip("/")
    api_key = posture_key or legacy_key
    raw_verify = os.getenv(
        "PFSENSE_POSTURE_API_VERIFY_SSL",
        os.getenv("PFSENSE_API_VERIFY_SSL", "true"),
    )
    verify_ssl = raw_verify.strip().lower() in _TRUE_VALUES
    credential_mode = "dedicated_posture" if dedicated else "legacy_shared"
    return base_url, api_key, verify_ssl, credential_mode


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
        message = f"{message}; verify CLOUDFLARE_ACCOUNT_ID is the Cloudflare Account ID (not a Zone ID) and that CLOUDFLARE_API_TOKEN is scoped to that account"

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

    statuses = [str(tunnel.get("status") or "unknown").lower() for tunnel in tunnels if isinstance(tunnel, dict)]
    unhealthy = [status for status in statuses if status in {"inactive", "degraded", "down"}]
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
    """Check pfSense REST API liveness with the posture read-only identity."""
    base_url, api_key, verify_ssl, credential_mode = _pfsense_posture_transport()
    if not base_url or not api_key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": ("PFSENSE_POSTURE_API_KEY (or legacy PFSENSE_API_KEY) and a pfSense API URL are not configured"),
            "probe": "pfsense_rest_api_v2",
            "credential_mode": credential_mode,
        }
    if not base_url.lower().startswith("https://"):
        return {
            "reachable": False,
            "error": "pfSense posture API URL must use HTTPS when API-key authentication is enabled",
            "probe": "pfsense_rest_api_v2",
            "credential_mode": credential_mode,
        }

    url = f"{base_url}{_PFSENSE_LIVENESS_PATH}"
    timeout = httpx.Timeout(
        connect=_PFSENSE_CONNECT_TIMEOUT_SEC,
        read=_PFSENSE_READ_TIMEOUT_SEC,
        write=_PFSENSE_CONNECT_TIMEOUT_SEC,
        pool=_PFSENSE_CONNECT_TIMEOUT_SEC,
    )
    started = time.monotonic()
    logger.debug(
        "pfSense API liveness probe started url=%s verify_ssl=%s credential_mode=%s connect_timeout_s=%s read_timeout_s=%s",
        url,
        verify_ssl,
        credential_mode,
        _PFSENSE_CONNECT_TIMEOUT_SEC,
        _PFSENSE_READ_TIMEOUT_SEC,
    )
    response: httpx.Response | None = None
    last_error: BaseException | None = None
    async with httpx.AsyncClient(
        timeout=timeout,
        verify=verify_ssl,
        follow_redirects=False,
    ) as client:
        for attempt in range(1, _PFSENSE_MAX_ATTEMPTS + 1):
            try:
                response = await client.get(
                    url,
                    headers={"X-API-Key": api_key, "Accept": "application/json"},
                )
                break
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt < _PFSENSE_MAX_ATTEMPTS and _http_error_kind(exc) in {
                    "connect_timeout",
                    "read_timeout",
                    "pool_timeout",
                    "timeout",
                    "connect_error",
                    "os_error",
                }:
                    await asyncio.sleep(_PFSENSE_RETRY_DELAY_SEC)
                    continue
                break

    if response is None:
        exc = last_error or RuntimeError("pfSense API request failed")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        error_kind = _http_error_kind(exc)
        failure_stage = _pfsense_failure_stage(error_kind)
        exception_type = type(exc).__name__
        error = _short_error(exc)
        if error_kind == "read_timeout":
            error = f"pfSense accepted the connection but did not return the REST API response within {_PFSENSE_READ_TIMEOUT_SEC:.0f}s"
        logger.warning(
            "pfSense API liveness probe failed url=%s verify_ssl=%s credential_mode=%s error_kind=%s failure_stage=%s exception_type=%s elapsed_ms=%s attempts=%s error=%s",
            url,
            verify_ssl,
            credential_mode,
            error_kind,
            failure_stage,
            exception_type,
            elapsed_ms,
            _PFSENSE_MAX_ATTEMPTS,
            error,
        )
        return {
            "reachable": False,
            "error": error,
            "error_kind": error_kind,
            "failure_stage": failure_stage,
            "exception_type": exception_type,
            "elapsed_ms": elapsed_ms,
            "attempts": _PFSENSE_MAX_ATTEMPTS,
            "probe": "pfsense_rest_api_v2",
            "path": _PFSENSE_LIVENESS_PATH,
            "url": url,
            "verify_ssl": verify_ssl,
            "credential_mode": credential_mode,
            "tls_trusted": False if not verify_ssl else None,
        }

    elapsed_ms = round((time.monotonic() - started) * 1000)
    healthy = 200 <= response.status_code < 400
    logger.debug(
        "pfSense API liveness probe completed url=%s verify_ssl=%s credential_mode=%s http_status=%s elapsed_ms=%s reachable=%s",
        url,
        verify_ssl,
        credential_mode,
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
        "credential_mode": credential_mode,
        "attempts": 1 if last_error is None else 2,
        "tls_trusted": True if verify_ssl and url.lower().startswith("https://") else False,
    }
    if not healthy:
        result["error"] = f"pfSense API returned HTTP {response.status_code}"
    return result


async def get_pfsense_api_snapshot() -> dict[str, Any]:
    """Cache pfSense checks and serve the last good result on transient failure."""
    global _pfsense_cache, _pfsense_cache_at

    async with _pfsense_cache_lock:
        age = time.monotonic() - _pfsense_cache_at
        if _pfsense_cache is not None and age < _PFSENSE_CACHE_TTL_SEC:
            return deepcopy(_pfsense_cache)

        previous = _pfsense_cache
        refreshed = await check_pfsense_api()
        if refreshed.get("reachable") is True or previous is None:
            _pfsense_cache = refreshed
        elif previous.get("reachable") is True:
            _pfsense_cache = {
                **previous,
                "stale": True,
                "refresh_error": refreshed.get("error", "pfSense refresh failed"),
                "last_success_at": previous.get("last_success_at"),
            }
        else:
            _pfsense_cache = refreshed

        if _pfsense_cache.get("reachable") is True and not _pfsense_cache.get("stale"):
            _pfsense_cache["last_success_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        _pfsense_cache_at = time.monotonic()
        return deepcopy(_pfsense_cache)


async def reset_pfsense_api_cache() -> None:
    """Reset the pfSense cache for deterministic tests."""
    global _pfsense_cache, _pfsense_cache_at
    async with _pfsense_cache_lock:
        _pfsense_cache = None
        _pfsense_cache_at = 0.0


async def enrich_optional_platform_checks(payload: dict[str, Any]) -> dict[str, Any]:
    """Add optional platform checks without changing required health semantics."""
    cloudflare, pfsense = await asyncio.gather(
        check_cloudflare_tunnels(),
        get_pfsense_api_snapshot(),
    )
    checks = dict(payload.get("checks") or {})
    checks["cloudflare"] = cloudflare
    checks["pfsense"] = pfsense
    return {**payload, "checks": checks}
