"""Optional Pydantic Logfire instrumentation for the FastAPI application."""

import os
from collections.abc import Mapping
from typing import Any

import logfire
from fastapi import FastAPI, Request, WebSocket

from nabla.utils.logger import logger

LOGFIRE_BASE_URL = "https://logfire-eu.pydantic.dev"
_EXCLUDED_URLS = r".*/(?:health|healthz|sickz|metrics)(?:\?.*)?$"


def _discard_request_attributes(
    _request: Request | WebSocket,
    _attributes: Mapping[str, Any],
) -> None:
    """Avoid recording validated request values or validation inputs."""
    return None


def configure_logfire(
    app: FastAPI,
    *,
    service_name: str,
    service_version: str,
) -> bool:
    """Configure Logfire when a write token is present without blocking startup."""
    token = os.getenv("LOGFIRE_TOKEN", "").strip()
    if not token:
        logger.info("Logfire disabled: LOGFIRE_TOKEN is not configured")
        return False

    try:
        logfire.configure(
            token=token,
            send_to_logfire=True,
            service_name=service_name,
            service_version=service_version,
            environment=os.getenv("LOGFIRE_ENVIRONMENT"),
            advanced=logfire.AdvancedOptions(base_url=LOGFIRE_BASE_URL),
        )
        logfire.instrument_fastapi(
            app,
            capture_headers=False,
            excluded_urls=_EXCLUDED_URLS,
            request_attributes_mapper=_discard_request_attributes,
        )
    except Exception:
        logger.exception("Logfire configuration failed; application startup will continue")
        return False

    logger.info("Logfire instrumentation enabled", service_name=service_name)
    return True
