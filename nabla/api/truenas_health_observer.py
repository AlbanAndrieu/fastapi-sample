"""Sanitized TrueNAS API configuration and authentication health observation."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import os
import re
import ssl
import time
from typing import Any

from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.truenas_client import observe_truenas_api
from nabla.utils.logger import logger

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_SUCCESS_CACHE_TTL_SEC = 60.0
_FAILURE_CACHE_TTL_SEC = 120.0
_SENTRY_FAILURE_COOLDOWN_SEC = 900.0
_cache_lock = asyncio.Lock()
_cached_result: dict[str, Any] | None = None
_cached_at = 0.0
_last_good: dict[str, Any] | None = None
_last_success_at: str | None = None
_last_failure_signature: str | None = None
_last_failure_reported_at = 0.0


def truenas_http_verify_ssl() -> bool:
    """Return the TrueNAS TLS policy from the single canonical environment setting."""
    raw = os.getenv("TRUENAS_API_VERIFY_SSL", "true").strip()
    return raw.lower() in _TRUE_VALUES


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _configured_username() -> str:
    return (
        os.getenv("TRUENAS_API_USERNAME", "").strip()
        or os.getenv("TRUENAS_USERNAME", "").strip()
        or os.getenv("TRUENAS_USER", "").strip()
    )


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
    if any(marker in message for marker in ("unauthorized", "authentication", "api key")):
        return "authentication", "authentication"
    return "api", "exception"


def truenas_api_configuration_failure() -> dict[str, Any] | None:
    """Return a sanitized authentication configuration failure, if any."""
    username = _configured_username()
    api_key = os.getenv("TRUENAS_API_KEY", "").strip()
    if not username:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "missing_username",
            "error": "TrueNAS API username is missing; authentication cannot be attempted.",
            "username_configured": False,
            "api_key_configured": bool(api_key),
        }

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
    if re.fullmatch(r"[0-9]+-.+", api_key) is None:
        return {
            "reachable": False,
            "phase": "authentication",
            "stage": "invalid_api_key_format",
            "error": "TRUENAS_API_KEY does not match the expected <id>-<key> format.",
            "username_configured": True,
            "api_key_configured": True,
        }
    return None


def _cache_ttl(result: dict[str, Any]) -> float:
    return _SUCCESS_CACHE_TTL_SEC if result.get("reachable") is True else _FAILURE_CACHE_TTL_SEC


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


def _stale_last_good() -> dict[str, Any] | None:
    if _last_good is None:
        return None
    return {
        "version": _last_good.get("version"),
        "apps": deepcopy(_last_good.get("apps")),
        "last_success_at": _last_success_at,
    }


async def observe_truenas_health_api() -> dict[str, Any]:
    """Run a cached official API probe after sanitized configuration validation."""
    global _cached_at, _cached_result, _last_good, _last_success_at

    configuration_failure = truenas_api_configuration_failure()
    if configuration_failure is not None:
        logger.error(
            "TrueNAS API authentication unavailable stage=%s error=%s",
            configuration_failure["stage"],
            configuration_failure["error"],
        )
        return configuration_failure

    async with _cache_lock:
        now = time.monotonic()
        if _cached_result is not None and now - _cached_at < _cache_ttl(_cached_result):
            cached = deepcopy(_cached_result)
            cached["cached"] = True
            cached["cache_age_seconds"] = round(now - _cached_at, 3)
            return cached

        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(observe_truenas_api)
            if not isinstance(result, dict):
                raise RuntimeError("TrueNAS API probe returned no health payload")
            result = dict(result)
            result.setdefault("phase", "call")
            result.setdefault("stage", "ok")
            result.setdefault(
                "elapsed_ms",
                max(0, round((time.perf_counter() - started) * 1000)),
            )
            result["cached"] = False
            result["stale"] = False
            if result.get("reachable") is True:
                _last_success_at = _utc_now()
                result["last_success_at"] = _last_success_at
                _last_good = deepcopy(result)
            _cached_result = result
            _cached_at = time.monotonic()
            return deepcopy(result)
        except Exception as exc:  # Adapter/network/auth errors are health data.
            elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
            phase, stage = _failure_kind(exc)
            error = _short_error(exc)
            stale = _stale_last_good()
            failure = {
                "reachable": False,
                "phase": phase,
                "stage": stage,
                "elapsed_ms": elapsed_ms,
                "error": error,
                "exception_type": exc.__class__.__name__,
                "cached": False,
                "stale": stale is not None,
                "retry_after_seconds": int(_FAILURE_CACHE_TTL_SEC),
                "username_configured": True,
                "api_key_configured": True,
            }
            if stale is not None:
                failure["last_good"] = stale
                failure["last_success_at"] = _last_success_at
            logger.warning(
                "truenas_api_health_probe_failed",
                phase=phase,
                stage=stage,
                exception_type=exc.__class__.__name__,
                elapsed_ms=elapsed_ms,
            )
            _report_failure_to_sentry(exc, f"{phase}:{stage}:{exc.__class__.__name__}")
            _cached_result = failure
            _cached_at = time.monotonic()
            return deepcopy(failure)


async def reset_truenas_health_cache() -> None:
    """Reset process-local cache/reporting state for deterministic tests."""
    global _cached_at, _cached_result, _last_good, _last_success_at
    global _last_failure_reported_at, _last_failure_signature
    async with _cache_lock:
        _cached_result = None
        _cached_at = 0.0
        _last_good = None
        _last_success_at = None
        _last_failure_signature = None
        _last_failure_reported_at = 0.0
