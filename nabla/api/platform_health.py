"""Optional platform health probes for Cloudflare Tunnel and pfSense."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from nabla.api.cloudflare_health import (
    check_cloudflare_tunnels,
    get_cloudflare_tunnels_snapshot,
    reset_cloudflare_api_cache,
)
from nabla.api.external_probe_cache import ProbeCacheResult, get_or_refresh_probe, reset_probe_cache
from nabla.api.platform_health_diagnostics import (
    http_error_kind as _http_error_kind,
    pfsense_failure_stage as _pfsense_failure_stage,
    short_error as _short_error,
    utc_now as _utc_now,
)
from nabla.api.provider_probe_policies import PFSENSE_LIVENESS_CACHE_POLICY as _PFSENSE_CACHE_POLICY
from nabla.api.runtime_environment import fastapi_cloud_runtime_detected
from nabla.settings.homelab import (
    PfSensePostureProviderSettings,
    pfsense_invalid_configuration_variables,
)

_PFSENSE_LIVENESS_PATH = "/api/v2/system/version"
_PFSENSE_CONNECT_TIMEOUT_SEC = 2.0
_PFSENSE_READ_TIMEOUT_SEC = 4.0
_PFSENSE_MAX_ATTEMPTS = 1
_PFSENSE_RETRY_DELAY_SEC = 0.2
_PFSENSE_CACHE_KEY = "pfsense:liveness"
_PFSENSE_TRANSIENT_ERROR_KINDS = frozenset(
    {
        "connect_timeout",
        "read_timeout",
        "pool_timeout",
        "timeout",
        "connect_error",
        "os_error",
    },
)
logger = logging.getLogger(__name__)


def _pfsense_posture_transport() -> tuple[str, str, bool, str]:
    """Resolve validated posture transport with the dedicated identity preferred."""
    provider = PfSensePostureProviderSettings()
    return (
        provider.base_url,
        provider.api_key,
        provider.verify_ssl,
        provider.credential_mode,
    )


def _cloud_transport_unconfirmed(error_kind: str) -> bool:
    """Return whether a transport failure is only cloud-vantage uncertainty."""
    return fastapi_cloud_runtime_detected() and error_kind in _PFSENSE_TRANSIENT_ERROR_KINDS


def _pfsense_transport_failure_result(
    exc: BaseException,
    *,
    elapsed_ms: int,
    attempts: int,
    url: str,
    verify_ssl: bool,
    credential_mode: str,
) -> dict[str, Any]:
    """Map transport failure into runtime-aware pfSense evidence."""
    error_kind = _http_error_kind(exc)
    error = _short_error(exc)
    if error_kind == "read_timeout":
        error = f"pfSense accepted the connection but did not return the REST API response within {_PFSENSE_READ_TIMEOUT_SEC:.0f}s"
    failure_stage = _pfsense_failure_stage(error_kind)
    cloud_unconfirmed = _cloud_transport_unconfirmed(error_kind)
    logger.warning(
        "pfSense API liveness probe failed error_kind=%s failure_stage=%s exception_type=%s elapsed_ms=%s attempts=%s cloud_unconfirmed=%s",
        error_kind,
        failure_stage,
        type(exc).__name__,
        elapsed_ms,
        attempts,
        cloud_unconfirmed,
    )
    result: dict[str, Any] = {
        "reachable": None if cloud_unconfirmed else False,
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
    if cloud_unconfirmed:
        result.update(
            {
                "state": "unknown",
                "status_confirmed": False,
                "degraded": False,
                "vantage_point": "fastapi_cloud",
                "warning": f"⚠️ pfSense status could not be confirmed from FastAPI Cloud: {error}",
            },
        )
    return result


async def check_pfsense_api() -> dict[str, Any]:
    """Check pfSense REST API liveness with the posture read-only identity."""
    try:
        base_url, api_key, verify_ssl, credential_mode = _pfsense_posture_transport()
    except ValidationError as exc:
        return {
            "reachable": False,
            "configuration_stage": "invalid_configuration",
            "invalid_configuration_variables": pfsense_invalid_configuration_variables(exc),
            "error": "pfSense posture transport configuration is invalid",
            "probe": "pfsense_rest_api_v2",
        }
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
    logger.debug(
        "pfSense API liveness probe started path=%s verify_ssl=%s credential_mode=%s",
        _PFSENSE_LIVENESS_PATH,
        verify_ssl,
        credential_mode,
    )
    started = time.monotonic()
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
                retryable = _http_error_kind(exc) in _PFSENSE_TRANSIENT_ERROR_KINDS
                if attempt < _PFSENSE_MAX_ATTEMPTS and retryable:
                    await asyncio.sleep(_PFSENSE_RETRY_DELAY_SEC)
                    continue
                break

    elapsed_ms = round((time.monotonic() - started) * 1000)
    if response is None:
        return _pfsense_transport_failure_result(
            last_error or RuntimeError("pfSense API request failed"),
            elapsed_ms=elapsed_ms,
            attempts=attempts,
            url=url,
            verify_ssl=verify_ssl,
            credential_mode=credential_mode,
        )

    healthy = 200 <= response.status_code < 400
    result = {
        "reachable": healthy,
        "status_confirmed": True,
        "state": "ok" if healthy else "fail",
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
        result.update(
            {
                "error": f"pfSense API returned HTTP {response.status_code}",
                "error_kind": f"http_{response.status_code}",
                "failure_stage": "http_response",
            },
        )
    logger.debug(
        "pfSense API liveness probe completed http_status=%s elapsed_ms=%s attempts=%s verify_ssl=%s",
        response.status_code,
        elapsed_ms,
        attempts,
        verify_ssl,
    )
    return result


def _cache_with_stale_evidence(cached: ProbeCacheResult) -> dict[str, Any]:
    value = dict(cached.value)
    current_failure = value.get("reachable") is False
    current_unconfirmed = value.get("status_confirmed") is False
    stale_refresh = cached.metadata.get("stale") is True
    use_last_good = (current_failure or current_unconfirmed or stale_refresh) and cached.last_good is not None
    if use_last_good:
        current_warning = value.get("warning")
        value = {
            **cached.last_good,
            "refresh_error": value.get("error") or "probe refresh is in progress",
        }
        if current_warning:
            value["refresh_warning"] = current_warning
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


async def reset_pfsense_api_cache() -> None:
    """Reset pfSense provider cache for deterministic tests."""
    await reset_probe_cache(_PFSENSE_CACHE_KEY)


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


__all__ = [
    "check_cloudflare_tunnels",
    "check_pfsense_api",
    "enrich_optional_platform_checks",
    "get_cloudflare_tunnels_snapshot",
    "get_pfsense_api_snapshot",
    "reset_cloudflare_api_cache",
    "reset_pfsense_api_cache",
]
