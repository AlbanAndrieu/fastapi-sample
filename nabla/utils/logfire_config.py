"""Optional Pydantic Logfire instrumentation for the FastAPI application."""

import os
from collections.abc import Mapping
from importlib import import_module
from typing import Any

from fastapi import FastAPI, Request, WebSocket

from nabla.utils.logger import enable_logfire_processor, logger

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
        logger.warning("Logfire disabled: LOGFIRE_TOKEN is not configured")
        return False

    # LangGraph/DeepAgents can emit GenAI telemetry through OpenTelemetry.
    # Keep prompt, completion and tool content disabled unless explicitly
    # approved later; timing and non-content metadata remain observable.
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")

    try:
        # FastAPI Cloud provides LOGFIRE_TOKEN. Let the Logfire SDK resolve the
        # appropriate ingestion endpoint instead of forcing a region/base URL.
        logfire = import_module("logfire")
        logfire.configure(
            token=token,
            send_to_logfire=True,
            service_name=service_name,
            service_version=service_version,
            environment=os.getenv("LOGFIRE_ENVIRONMENT"),
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
            service_name=service_name,
        )
        return False

    logger.info(
        "Logfire instrumentation enabled",
        service_name=service_name,
        service_version=service_version,
        environment=os.getenv("LOGFIRE_ENVIRONMENT"),
        token_present=True,
        system_metrics=True,
        genai_content_capture=False,
    )
    return True
