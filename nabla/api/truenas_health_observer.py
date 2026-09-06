"""Sanitized TrueNAS API configuration and authentication health observation."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import re
import ssl
import time
from typing import Any

from nabla.api.external_probe_cache import get_or_refresh_probe, reset_probe_cache
from nabla.api.provider_probe_policies import (
    TRUENAS_API_CACHE_POLICY as _CACHE_POLICY,
)
from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.truenas_client import observe_truenas_api
from nabla.settings.homelab import TrueNASProviderSettings
from nabla.utils.logger import logger

_CACHE_KEY = "truenas:api"
_TRUENAS_PROBE_DEADLINE_SEC = 8.0
_SENTRY_FAILURE_COOLDOWN_SEC = 900.0
_last_failure_signature: str | None = None
_last_failure_reported_at = 0.0


def truenas_http_verify_ssl() -> bool:
    """Return the canonical validated TrueNAS TLS policy."""
    return TrueNASProviderSettings().verify_ssl


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _configured_username() -> str:
    return TrueNASProviderSettings().adapter_username


def _failure_kind(exc: BaseException) -> tuple[str, str]:
    """Classify the failure without leaking credentials or transport internals."""
    message = str(exc).casefold()
    class_name = exc.__class__.__name__.casefold()
    if isinstance(exc, ConnectionResetError):
        return "connect", "connection_reset"
    if isinstance(exc, TimeoutError) and "handshake" in message:
        return "connect", "tls_handshake_timeout"
    if isinstance(exc, ssl.SSLError):
        return "connect", "tls_error"
    if "calltimeout" in class_name:
        return "api", "api_call_timeout"
    if isinstance(exc, TimeoutError) or "timeout" in class_name:
        return "connect", "connect_timeout"
    if any(
        marker in message
        for marker in (
            "you are not allowed to access this resource",
            "policy violation",
        )
    ):
        return "connect", "source_allowlist"
    if any(
        marker in message for marker in ("unauthorized", "authentication", "api key")
    ):
        return "authentication", "authentication"
    if "websocket" in message:
        return "connect", "websocket"
    return "api", "exception"


def truenas_api_configuration_failure() -> dict[str, Any] | None:
    """Return a sanitized authentication configuration failure, if any."""
    settings = TrueNASProviderSettings()
    username = settings.adapter_username
    api_key = settings.canonical_api_key
    if not username:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "missing_username",
            "error": "TrueNAS API username is missing; authentication cannot be attempted.",
            "username_configured": False,
            "api_key_configured": bool(api_key),
        }

    # The health contract intentionally requires the canonical TRUENAS_API_KEY.
    # TRUENAS_MCP_API_KEY remains a lower-level adapter compatibility fallback only.
    credential_status = inspect_environment_credentials(
        "truenas",
        "TRUENAS_API_KEY",
        secret_variables=frozenset({"TRUENAS_API_KEY"}),
    )
    if credential_status.missing_variables:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "missing_api_key",
            "error": "TRUENAS_API_KEY is missing; authentication cannot be attempted.",
            "username_configured": True,
            "api_key_configured": False,
        }
    if credential_status.invalid_reference_variables:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "invalid_api_key_reference",
            "error": (
                "TRUENAS_API_KEY contains an environment-variable name instead of "
                "raw TrueNAS API key material."
            ),
            "username_configured": True,
            "api_key_configured": True,
        }
    if re.fullmatch(r"[0-9]+-[A-Za-z0-9]{64}", api_key) is None:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "invalid_api_key_format",
            "error": (
                "TRUENAS_API_KEY does not match the expected "
                "<id>-<64-character-alphanumeric-key> format."
            ),
            "username_configured": True,
            "api_key_configured": True,
        }
    return None


def _should_report_failure(signature: str) -> bool:
    global _last_failure_reported_at, _last_failure_signature
    now = time.monotonic()
    should_report = (
        signature != _last_failure_signature
        or now - _last_failure_reported_at >= _SENTRY_FAILURE_COOLDOWN_SEC
    )
    if should_report:
        _last_failure_signature = signature
        _last_failure_reported_at = now
    return should_report


def _report_failure_to_sentry(exc: BaseException, signature: str) -> None:
    if not _should_report_failure(signature):
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception as report_exc:  # pragma: no cover - observability must not break health.
        logger.warning(
            "truenas_sentry_report_failed",
            exception_type=type(report_exc).__name__,
        )


def _last_good_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": value.get("version"),
        "apps": deepcopy(value.get("apps")),
        "last_success_at": value.get("last_success_at"),
    }


async def _probe_origin() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(observe_truenas_api),
            timeout=_TRUENAS_PROBE_DEADLINE_SEC,
        )
        if not isinstance(result, dict):
            raise RuntimeError("TrueNAS API probe returned no health payload")
        value = dict(result)
        value.setdefault("phase", "call")
        value.setdefault("stage", "ok")
        value.setdefault(
            "elapsed_ms",
            max(0, round((time.perf_counter() - started) * 1000)),
        )
        if value.get("reachable") is True:
            value["last_success_at"] = _utc_now()
        return value
    except Exception as exc:  # Adapter/network/auth errors are health data.
        elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
        phase, stage = _failure_kind(exc)
        logger.debug(
            "truenas_api_health_probe_classified",
            phase=phase,
            stage=stage,
            exception_type=exc.__class__.__name__,
            elapsed_ms=elapsed_ms,
        )
        _report_failure_to_sentry(exc, f"{phase}:{stage}:{exc.__class__.__name__}")
        return {
            "reachable": False,
            "phase": phase,
            "stage": stage,
            "elapsed_ms": elapsed_ms,
            "error": _short_error(exc),
            "exception_type": exc.__class__.__name__,
            "retry_after_seconds": int(_CACHE_POLICY.failure_ttl),
            "username_configured": True,
            "api_key_configured": True,
        }


def _apply_cache_evidence(
    value: dict[str, Any],
    *,
    metadata: dict[str, Any],
    last_good: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(value)
    result.update(metadata)
    stale_refresh = metadata.get("stale") is True
    refresh_in_progress = metadata.get("refresh_in_progress") is True
    current_failure = result.get("reachable") is not True

    if stale_refresh and refresh_in_progress:
        evidence = last_good or value
        result = {
            "reachable": False,
            "phase": "cache",
            "stage": "refresh_in_progress",
            "error": "A peer runtime is refreshing the TrueNAS API; last-known-good evidence is stale.",
            **metadata,
            "stale": True,
            "last_good": _last_good_payload(evidence),
            "last_success_at": evidence.get("last_success_at"),
        }
    elif current_failure and last_good is not None:
        result["stale"] = True
        result["last_good"] = _last_good_payload(last_good)
        result["last_success_at"] = last_good.get("last_success_at")
    else:
        result["stale"] = False
    return result


async def observe_truenas_health_api() -> dict[str, Any]:
    """Run the official TrueNAS probe through local and shared Redis caches."""
    settings = TrueNASProviderSettings()
    configuration_failure = truenas_api_configuration_failure()
    if configuration_failure is not None:
        logger.error(
            "TrueNAS API authentication unavailable stage=%s error=%s",
            configuration_failure["stage"],
            configuration_failure["error"],
        )
        return configuration_failure

    cached = await get_or_refresh_probe(
        _CACHE_KEY,
        _probe_origin,
        is_success=lambda value: value.get("reachable") is True,
        policy=_CACHE_POLICY,
    )
    result = _apply_cache_evidence(
        cached.value,
        metadata=cached.metadata,
        last_good=cached.last_good,
    )
    result["credential_selection"] = {
        "username_variable": settings.adapter_username_environment,
        "api_key_variable": settings.adapter_api_key_environment,
        "shadowed_username_variables": list(settings.shadowed_username_environments),
        "shadowed_api_key_variables": list(settings.shadowed_api_key_environments),
    }
    return result


async def reset_truenas_health_cache() -> None:
    """Reset process-local probe cache/reporting state for deterministic tests."""
    global _last_failure_reported_at, _last_failure_signature
    await reset_probe_cache(_CACHE_KEY)
    _last_failure_signature = None
    _last_failure_reported_at = 0.0
