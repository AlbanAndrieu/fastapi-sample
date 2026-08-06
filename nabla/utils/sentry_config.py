"""Safe Sentry configuration with local-first delivery."""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from nabla._version import get_versions

_logger = logging.getLogger(__name__)
_DEFAULT_LOCAL_SENTRY_PORT = 9000
DEFAULT_SENTRY_DSN = "https://11c5d815632831d3274c830441885207@o4505783360356352.ingest.us.sentry.io/4505783364681728"
_FILTERED_VALUE = "[Filtered]"
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "secret",
        "set-cookie",
        "token",
        "x-api-key",
    },
)
_IGNORED_TRANSACTION_PATHS = frozenset({"/health", "/healthz", "/metrics", "/sickz"})


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return min(max(float(env.get(name, default)), 0.0), 1.0)
    except (TypeError, ValueError):
        return default


def _derived_local_dsn(cloud_dsn: str) -> str:
    """Reuse the configured DSN credentials against self-hosted Sentry."""
    if not cloud_dsn:
        return ""
    parsed = urlsplit(cloud_dsn)
    if not parsed.hostname:
        return ""
    userinfo = parsed.username or ""
    if parsed.password:
        userinfo += f":{parsed.password}"
    if userinfo:
        userinfo += "@"
    return urlunsplit(
        (
            parsed.scheme or "http",
            f"{userinfo}localhost:{_DEFAULT_LOCAL_SENTRY_PORT}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        ),
    )


def sentry_dsn_is_reachable(dsn: str, *, timeout: float = 0.25) -> bool:
    try:
        parsed = urlsplit(dsn)
        if not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def select_sentry_dsn(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Prefer reachable self-hosted Sentry, then fall back to the cloud DSN."""
    values = os.environ if env is None else env
    cloud_dsn = values.get("SENTRY_DSN", DEFAULT_SENTRY_DSN).strip()
    local_dsn = values.get("SENTRY_LOCAL_DSN", "").strip() or _derived_local_dsn(cloud_dsn)

    if local_dsn and sentry_dsn_is_reachable(local_dsn):
        return local_dsn, "local"
    if cloud_dsn:
        return cloud_dsn, "cloud"
    return "", "disabled"


def _scrub_sensitive(value: Any) -> Any:
    """Return a copy with common credential fields removed."""
    if isinstance(value, dict):
        return {key: _FILTERED_VALUE if str(key).lower() in _SENSITIVE_KEYS else _scrub_sensitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_sensitive(item) for item in value)
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    return _scrub_sensitive(deepcopy(event))


def _before_send_log(log: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    return _scrub_sensitive(deepcopy(log))


def _before_send_transaction(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    request_url = str(event.get("request", {}).get("url", ""))
    path = urlsplit(request_url).path
    transaction = str(event.get("transaction", ""))
    if path in _IGNORED_TRANSACTION_PATHS or transaction in _IGNORED_TRANSACTION_PATHS:
        return None
    return _scrub_sensitive(deepcopy(event))


def _integrations(*, include_logging: bool, include_ai: bool = False) -> list[Any]:
    integrations: list[Any] = []
    if include_ai:
        for module_name, class_name in (
            ("sentry_sdk.integrations.litellm", "LiteLLMIntegration"),
            ("sentry_sdk.integrations.langchain", "LangchainIntegration"),
            ("sentry_sdk.integrations.langgraph", "LanggraphIntegration"),
            ("sentry_sdk.integrations.openai", "OpenAIIntegration"),
            ("sentry_sdk.integrations.mcp", "MCPIntegration"),
        ):
            try:
                module = __import__(module_name, fromlist=[class_name])
                integrations.append(getattr(module, class_name)())
            except Exception as exc:
                _logger.debug("Skipping Sentry integration %s.%s: %s", module_name, class_name, exc)

    integrations.extend(
        [
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )
    if include_logging:
        integrations.append(
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        )
    return integrations


def configure_sentry(env: Mapping[str, str] | None = None) -> bool:
    """Initialize Sentry without making application startup depend on telemetry."""
    values = os.environ if env is None else env
    if values.get("SENTRY_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        _logger.info("Sentry is disabled by SENTRY_ENABLED")
        return False
    dsn, target = select_sentry_dsn(values)
    if not dsn:
        _logger.info("Sentry is disabled: no DSN configured")
        return False

    logfire_enabled = bool(values.get("LOGFIRE_TOKEN", "").strip())
    app_name = values.get("APP_NAME", "fastapi-sample")
    app_version = get_versions()["version"]
    try:
        sentry_sdk.init(
            dsn=dsn,
            enable_logs=not logfire_enabled,
            traces_sample_rate=(None if logfire_enabled else _env_float(values, "SENTRY_TRACES_SAMPLE_RATE", 0.1)),
            profiles_sample_rate=(0.0 if logfire_enabled else _env_float(values, "SENTRY_PROFILES_SAMPLE_RATE", 0.0)),
            sample_rate=_env_float(values, "SENTRY_ERROR_SAMPLE_RATE", 1.0),
            send_default_pii=False,
            before_send=_before_send,
            before_send_log=_before_send_log,
            before_send_transaction=_before_send_transaction,
            ignore_errors=[BrokenPipeError, ConnectionResetError, TimeoutError],
            max_breadcrumbs=int(values.get("SENTRY_MAX_BREADCRUMBS", "50")),
            shutdown_timeout=float(values.get("SENTRY_SHUTDOWN_TIMEOUT", "2")),
            environment=values.get("SENTRY_ENVIRONMENT") or values.get("ENV") or "development",
            release=values.get("SENTRY_RELEASE") or app_version,
            integrations=_integrations(
                include_logging=not logfire_enabled,
                include_ai=values.get("SENTRY_AI_INTEGRATIONS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
            ),
            server_name=app_name,
        )
    except Exception:
        _logger.exception("Sentry initialization failed; application will continue")
        return False

    _logger.info(
        "Sentry initialized with %s target; logs and tracing are %s",
        target,
        "disabled because Logfire is enabled" if logfire_enabled else "enabled",
    )
    return True
