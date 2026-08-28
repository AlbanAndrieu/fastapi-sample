"""Sanitized TrueNAS API configuration and authentication health observation."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.truenas_client import observe_truenas_api
from nabla.utils.logger import logger

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def truenas_http_verify_ssl() -> bool:
    """Return the TrueNAS TLS policy from the single canonical environment setting."""
    raw = os.getenv("TRUENAS_API_VERIFY_SSL", "true").strip()
    return raw.lower() in _TRUE_VALUES


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


def _configured_username() -> str:
    return (
        os.getenv("TRUENAS_API_USERNAME", "").strip()
        or os.getenv("TRUENAS_USERNAME", "").strip()
        or os.getenv("TRUENAS_USER", "").strip()
    )


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


async def observe_truenas_health_api() -> dict[str, Any]:
    """Run the official read-only API probe after sanitized configuration validation."""
    configuration_failure = truenas_api_configuration_failure()
    if configuration_failure is not None:
        logger.error(
            "TrueNAS API authentication unavailable stage=%s error=%s",
            configuration_failure["stage"],
            configuration_failure["error"],
        )
        return configuration_failure

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
        return result
    except Exception as exc:  # Adapter/network/auth errors are health data and Sentry evidence.
        elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
        logger.exception("TrueNAS API health probe failed after configuration validation")
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)
        except Exception:  # pragma: no cover - observability must not break health reporting.
            logger.exception("Unable to report TrueNAS API failure to Sentry")
        return {
            "reachable": False,
            "phase": "api",
            "stage": "exception",
            "elapsed_ms": elapsed_ms,
            "error": _short_error(exc),
            "username_configured": True,
            "api_key_configured": True,
        }
