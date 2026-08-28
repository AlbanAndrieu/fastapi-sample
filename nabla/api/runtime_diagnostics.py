"""Local-only runtime diagnostics exposed to the project MCP during development."""

from __future__ import annotations

import os
from pathlib import Path
import platform

from fastapi import APIRouter, Query

from nabla.config_settings import APP_RUNTIME_VERSION
from nabla.utils.runtime_logs import (
    get_runtime_errors,
    get_runtime_logs,
    runtime_log_metadata,
)

router = APIRouter(prefix="/v1/runtime")


@router.get("/metadata", operation_id="get_runtime_metadata")
def get_runtime_metadata() -> dict[str, object]:
    """Return local development process metadata and log-buffer state."""
    return {
        "runtime_version": APP_RUNTIME_VERSION,
        "python_version": platform.python_version(),
        "pid": os.getpid(),
        "project_path": str(Path.cwd()),
        "log_buffer": runtime_log_metadata(),
    }


@router.get("/logs", operation_id="get_runtime_logs")
def read_runtime_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    min_level: str | None = Query(default=None, max_length=16),
    contains: str | None = Query(default=None, max_length=128),
) -> dict[str, object]:
    """Return a bounded slice of recent local FastAPI/Gunicorn/Uvicorn logs."""
    events = get_runtime_logs(limit=limit, min_level=min_level, contains=contains)
    return {
        "events": events,
        "returned": len(events),
        "buffer": runtime_log_metadata(),
    }


@router.get("/errors", operation_id="get_runtime_errors")
def read_runtime_errors(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    """Return recent ERROR/CRITICAL events for an agent debugging loop."""
    events = get_runtime_errors(limit=limit)
    return {
        "events": events,
        "returned": len(events),
        "buffer": runtime_log_metadata(),
    }
