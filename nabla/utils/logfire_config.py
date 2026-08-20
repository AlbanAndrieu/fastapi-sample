"""Optional Pydantic Logfire instrumentation for the FastAPI application."""

import os
from collections.abc import Mapping
from importlib import import_module
from typing import Any

from fastapi import FastAPI, Request, WebSocket

from nabla.utils.logger import enable_logfire_processor, logger

LOGFIRE_BASE_URL = os.getenv(
    "LOGFIRE_BASE_URL",
    "https://logfire-eu.pydantic.dev",
).rstrip("/")
_EXCLUDED_URLS = (
    r".*/(?:docs(?:/oauth2-redirect)?|health|healthz|logs(?:/.*)?|metrics|"
    r"openapi\.json|ping|redoc|sickz|stream(?:/.*)?|llm(?:/.*)?|"
    r"v1/mcp(?:/.*)?)(?:\?.*)?$"
)
_FALSE_VALUES = {"0", "false", "no", "off"}


def _discard_request_attributes(
    _request: Request | WebSocket,
    _attributes: Mapping[str, Any],
) -> dict[str, Any]:
    """Avoid recording validated request values or validation inputs."""
    return {}


def configure_logfire(
    app: FastAPI,
    *,
    service_name: str,
    service_version: str,
) -> bool:
    """Configure Logfire when a write token is present without blocking startup."""
    enabled = os.getenv("LOGFIRE_ENABLED", "true").strip().lower()
    if enabled in _FALSE_VALUES:
        logger.info("Logfire disabled by LOGFIRE_ENABLED")
        return False

    token = os.getenv("LOGFIRE_TOKEN", "").strip()
    if not token:
        logger.warning(
            "Logfire disabled: LOGFIRE_TOKEN is not configured",
            logfire_base_url=LOGFIRE_BASE_URL,
        )
        return False

    # LangGraph/DeepAgents can emit GenAI telemetry through OpenTelemetry.
    # Keep prompt, completion and tool content disabled unless explicitly
    # approved later; timing and non-content metadata remain observable.
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")

    try:
        # Keep the SDK completely inactive unless explicit credentials are
        # provided. This also avoids import-time telemetry side effects in
        # tests and local development.
        logfire = import_module("logfire")
        logfire.configure(
            token=token,
            send_to_logfire=True,
            service_name=service_name,
            service_version=service_version,
            environment=os.getenv("LOGFIRE_ENVIRONMENT"),
            advanced=logfire.AdvancedOptions(base_url=LOGFIRE_BASE_URL),
        )
        logfire.instrument_system_metrics()
        logfire.instrument_fastapi(
            app,
            capture_headers=False,
            excluded_urls=_EXCLUDED_URLS,
            request_attributes_mapper=_discard_request_attributes,
        )
        enable_logfire_processor(logfire.StructlogProcessor())
    except Exception:
        logger.exception(
            "Logfire configuration failed; application startup will continue",
            logfire_base_url=LOGFIRE_BASE_URL,
            service_name=service_name,
        )
        return False

    logger.info(
        "Logfire instrumentation enabled",
        service_name=service_name,
        service_version=service_version,
        logfire_base_url=LOGFIRE_BASE_URL,
        system_metrics=True,
        genai_content_capture=False,
    )
    return True
