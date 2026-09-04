"""Optional platform health probes for Cloudflare Tunnel and pfSense."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from nabla.api.cloudflare_tunnels import CloudflareTunnelSettings
from nabla.api.external_probe_cache import (
    ProbeCacheResult,
    get_or_refresh_probe,
    reset_probe_cache,
)
from nabla.api.provider_probe_policies import (
    CLOUDFLARE_TUNNELS_CACHE_POLICY as _CLOUDFLARE_CACHE_POLICY,
    PFSENSE_LIVENESS_CACHE_POLICY as _PFSENSE_CACHE_POLICY,
)
from nabla.api.platform_health_diagnostics import (
    http_error_kind as _http_error_kind,
    pfsense_failure_stage as _pfsense_failure_stage,
    short_error as _short_error,
    utc_now as _utc_now,
)

_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
_PFSENSE_LIVENESS_PATH = "/api/v2/system/version"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PFSENSE_CONNECT_TIMEOUT_SEC = 2.0
_PFSENSE_READ_TIMEOUT_SEC = 4.0
_PFSENSE_MAX_ATTEMPTS = 1
_PFSENSE_RETRY_DELAY_SEC = 0.2
_PFSENSE_CACHE_KEY = "pfsense:liveness"
_CLOUDFLARE_CACHE_KEY = "cloudflare:tunnels"
logger = logging.getLogger(__name__)


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
            "and CLOUDFLARE_API_TOKEN is scoped to that account"
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
        "last_success_at": _utc_now(),
    }


async def check_pfsense_api() -> dict[str, Any]:
    """Check pfSense REST API liveness with the posture read-only identity."""
    base_url, api_key, verify_ssl, credential_mode = _pfsense_posture_transport()
    if not base_url or not api_key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "PFSENSE_POSTURE_API_KEY and a pfSense API URL are not configured",
            "probe": "pfsense_rest_api_v2",
            "credential_mode": credential_mode,
        }
    if not base_url.lower().startswith("https://"):
        return {
            "reachable": False,
            "error": "pfSense posture API URL must use HTTPS with API-key authentication",
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
        "pfSense API liveness probe started url=%s verify_ssl=%s "
        "connect_timeout_s=%s read_timeout_s=%s",
        url,
        verify_ssl,
        _PFSENSE_CONNECT_TIMEOUT_SEC,
        _PFSENSE_READ_TIMEOUT_SEC,
    )
    response: httpx.Response | None = None
    last_error: BaseException | None = None
    attempts = 0
    async with httpx.AsyncClient(
        timeout=timeout,
        verify=verify_ssl,
        follow_redirects=False,
    ) as client:
        for attempt in range(1, _PFSENSE_MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                response = await client.get(
                    url,
                    headers={"X-API-Key": api_key, "Accept": "application/json"},
                )
                break
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                retryable = _http_error_kind(exc) in {
                    "connect_timeout",
                    "read_timeout",
                    "pool_timeout",
                    "timeout",
                    "connect_error",
                    "os_error",
                }
                if attempt < _PFSENSE_MAX_ATTEMPTS and retryable:
                    await asyncio.sleep(_PFSENSE_RETRY_DELAY_SEC)
                    continue
                break

    elapsed_ms = round((time.monotonic() - started) * 1000)
    if response is None:
        exc = last_error or RuntimeError("pfSense API request failed")
        error_kind = _http_error_kind(exc)
        error = _short_error(exc)
        if error_kind == "read_timeout":
            error = (
                "pfSense accepted the connection but did not return the REST API "
                f"response within {_PFSENSE_READ_TIMEOUT_SEC:.0f}s"
            )
        failure_stage = _pfsense_failure_stage(error_kind)
        logger.warning(
            "pfSense API liveness probe failed url=%s verify_ssl=%s "
            "error_kind=%s failure_stage=%s exception_type=%s "
            "elapsed_ms=%s attempts=%s",
            url,
            verify_ssl,
            error_kind,
            failure_stage,
            type(exc).__name__,
            elapsed_ms,
            attempts,
        )
        return {
            "reachable": False,
            "error": error,
            "error_kind": error_kind,
            "failure_stage": failure_stage,
            "exception_type": type(exc).__name__,
            "elapsed_ms": elapsed_ms,
            "attempts": attempts,
            "probe": "pfsense_rest_api_v2",
            "path": _PFSENSE_LIVENESS_PATH,
            "url": url,
            "verify_ssl": verify_ssl,
            "credential_mode": credential_mode,
            "tls_trusted": False if not verify_ssl else None,
        }

    healthy = 200 <= response.status_code < 400
    logger.debug(
        "pfSense API liveness probe completed url=%s verify_ssl=%s "
        "http_status=%s elapsed_ms=%s attempts=%s reachable=%s",
        url,
        verify_ssl,
        response.status_code,
        elapsed_ms,
        attempts,
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
        "attempts": attempts,
        "tls_trusted": verify_ssl,
    }
    if healthy:
        result["last_success_at"] = _utc_now()
    else:
        result["error"] = f"pfSense API returned HTTP {response.status_code}"
    return result


def _cache_with_stale_evidence(cached: ProbeCacheResult) -> dict[str, Any]:
    value = dict(cached.value)
    current_failure = value.get("reachable") is False or value.get("api_reachable") is False
    stale_refresh = cached.metadata.get("stale") is True
    use_last_good = (current_failure or stale_refresh) and cached.last_good is not None
    if use_last_good:
        error = value.get("error") or "probe refresh is in progress"
        value = {
            **cached.last_good,
            "refresh_error": error,
        }
    value.update(cached.metadata)
    value["stale"] = bool(use_last_good or stale_refresh)
    return value


async def get_pfsense_api_snapshot() -> dict[str, Any]:
    """Use L1/Redis L2 cache and stale-last-good for pfSense liveness."""
    cached = await get_or_refresh_probe(
        _PFSENSE_CACHE_KEY,
        check_pfsense_api,
        is_success=lambda value: value.get("reachable") is True,
        policy=_PFSENSE_CACHE_POLICY,
    )
    return _cache_with_stale_evidence(cached)


async def get_cloudflare_tunnels_snapshot() -> dict[str, Any]:
    """Use L1/Redis L2 cache for the Cloudflare control-plane query."""
    cached = await get_or_refresh_probe(
        _CLOUDFLARE_CACHE_KEY,
        check_cloudflare_tunnels,
        is_success=lambda value: value.get("api_reachable") is True,
        policy=_CLOUDFLARE_CACHE_POLICY,
    )
    return _cache_with_stale_evidence(cached)


async def reset_pfsense_api_cache() -> None:
    await reset_probe_cache(_PFSENSE_CACHE_KEY)


async def reset_cloudflare_api_cache() -> None:
    await reset_probe_cache(_CLOUDFLARE_CACHE_KEY)


async def enrich_optional_platform_checks(payload: dict[str, Any]) -> dict[str, Any]:
    """Add optional platform checks without changing required health semantics."""
    cloudflare, pfsense = await asyncio.gather(
        get_cloudflare_tunnels_snapshot(),
        get_pfsense_api_snapshot(),
    )
    checks = dict(payload.get("checks") or {})
    checks["cloudflare"] = cloudflare
    checks["pfsense"] = pfsense
    return {**payload, "checks": checks}
