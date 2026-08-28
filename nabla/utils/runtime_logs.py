"""Bounded, local-development runtime log capture for MCP diagnostics."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime
from itertools import count
import json
import logging
import os
import re
import sys
import threading
from typing import Any

_DEFAULT_CAPACITY = 1000
_MIN_CAPACITY = 100
_MAX_CAPACITY = 5000
_MAX_MESSAGE_CHARS = 4000
_MAX_EXCEPTION_CHARS = 12000
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def runtime_diagnostics_enabled() -> bool:
    """Enable diagnostics explicitly, or automatically for local reload servers."""
    configured = os.getenv("RUNTIME_DIAGNOSTICS_ENABLED")
    if configured is not None:
        return configured.strip().lower() in _TRUE_VALUES
    return "--reload" in sys.argv


def _capacity() -> int:
    raw = os.getenv("RUNTIME_DIAGNOSTICS_LOG_CAPACITY", str(_DEFAULT_CAPACITY)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_CAPACITY
    return max(_MIN_CAPACITY, min(value, _MAX_CAPACITY))


_LOGS: deque[dict[str, Any]] = deque(maxlen=_capacity())
_LOCK = threading.Lock()
_SEQUENCE = count(1)


def _mask_bearer(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _mask_bearer(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_bearer(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_bearer(item) for item in value)
    if isinstance(value, str):
        return _BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    return value


def _redact(value: Any) -> Any:
    """Apply the application redactor plus stricter bearer-token masking."""
    from nabla.utils.logger import _redact_value  # noqa: PLC2701

    return _mask_bearer(_redact_value(value))


def _truncate(value: Any, *, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[truncated]"


def _append(entry: dict[str, Any]) -> None:
    if not runtime_diagnostics_enabled():
        return
    safe_entry = _redact(entry)
    safe_entry["sequence"] = next(_SEQUENCE)
    safe_entry["timestamp"] = datetime.now(UTC).isoformat()
    with _LOCK:
        _LOGS.append(safe_entry)


def capture_structlog_event(
    _logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Capture an already-redacted structlog event and pass it through unchanged."""
    if not runtime_diagnostics_enabled():
        return event_dict

    copied = dict(event_dict)
    message = copied.pop("event", copied.pop("message", ""))
    level = str(copied.pop("level", method_name)).upper()
    exception = copied.pop("exception", copied.pop("exc_info", None))
    entry: dict[str, Any] = {
        "source": "structlog",
        "level": level,
        "logger": str(copied.pop("logger", "nabla")),
        "message": _truncate(message, limit=_MAX_MESSAGE_CHARS),
    }
    if exception:
        entry["exception"] = _truncate(exception, limit=_MAX_EXCEPTION_CHARS)
    if copied:
        entry["fields"] = copied
    _append(entry)
    return event_dict


class RuntimeLogHandler(logging.Handler):
    """Capture standard-library/Uvicorn/Gunicorn logs in the same bounded buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        if not runtime_diagnostics_enabled():
            return
        try:
            entry: dict[str, Any] = {
                "source": "logging",
                "level": record.levelname,
                "logger": record.name,
                "message": _truncate(record.getMessage(), limit=_MAX_MESSAGE_CHARS),
            }
            if record.exc_info:
                formatter = logging.Formatter()
                entry["exception"] = _truncate(
                    formatter.formatException(record.exc_info),
                    limit=_MAX_EXCEPTION_CHARS,
                )
            _append(entry)
        except Exception:
            # Logging handlers must never break the application or recursively log failures.
            return


def attach_runtime_log_handler(root_logger: logging.Logger) -> None:
    """Attach one diagnostics handler when local development diagnostics are enabled."""
    if not runtime_diagnostics_enabled():
        return
    if any(isinstance(handler, RuntimeLogHandler) for handler in root_logger.handlers):
        return
    handler = RuntimeLogHandler(level=logging.DEBUG)
    root_logger.addHandler(handler)


def _level_number(level: str) -> int:
    mapping = logging.getLevelNamesMapping()
    return int(mapping.get(level.upper(), logging.NOTSET))


def get_runtime_logs(
    *,
    limit: int = 200,
    min_level: str | None = None,
    contains: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent runtime logs in chronological order with bounded filtering."""
    bounded_limit = max(1, min(limit, 1000))
    threshold = _level_number(min_level) if min_level else logging.NOTSET
    needle = contains.casefold() if contains else None

    with _LOCK:
        snapshot = list(_LOGS)

    filtered: list[dict[str, Any]] = []
    for entry in snapshot:
        if _level_number(str(entry.get("level", ""))) < threshold:
            continue
        if needle:
            searchable = json.dumps(entry, default=str, ensure_ascii=False).casefold()
            if needle not in searchable:
                continue
        filtered.append(dict(entry))
    return filtered[-bounded_limit:]


def get_runtime_errors(*, limit: int = 100) -> list[dict[str, Any]]:
    """Return recent error/critical events for an agent debugging loop."""
    return get_runtime_logs(limit=limit, min_level="ERROR")


def runtime_log_metadata() -> dict[str, Any]:
    """Describe the in-process development log buffer without exposing log content."""
    with _LOCK:
        count_entries = len(_LOGS)
        oldest = _LOGS[0].get("timestamp") if _LOGS else None
        newest = _LOGS[-1].get("timestamp") if _LOGS else None
        capacity = _LOGS.maxlen
    return {
        "enabled": runtime_diagnostics_enabled(),
        "count": count_entries,
        "capacity": capacity,
        "oldest_timestamp": oldest,
        "newest_timestamp": newest,
    }


def clear_runtime_logs() -> None:
    """Clear captured events for deterministic tests; not exposed as an API/MCP tool."""
    with _LOCK:
        _LOGS.clear()
