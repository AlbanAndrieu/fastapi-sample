import logging
import os
import re
import sys
from collections.abc import Mapping

import structlog

from nabla.utils.runtime_logs import capture_structlog_event

logger = structlog.get_logger()

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|(?<![a-z])pass(?![a-z])|pwd|secret|token|"
    r"api[_-]?key|authorization|cookie|"
    r"instance[_-]?id|client[_-]?secret|credential)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?P<prefix>(?:password|passwd|pass|pwd|secret|token|api[_-]?key|"
    r"authorization|instance[_-]?id|client[_-]?secret)\s*[=:]\s*)"
    r"(?P<value>[^\s,;}&]+)"
)
_CONNECTION_PASSWORD = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://[^:/\s]+:)(?P<password>[^@/\s]+)(?=@)")


def _redact_value(value):
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        value = _CONNECTION_PASSWORD.sub(r"\g<scheme>[REDACTED]", value)
        return _SENSITIVE_VALUE.sub(r"\g<prefix>[REDACTED]", value)
    return value


def redact_sensitive_data(_, __, event_dict):
    return _redact_value(event_dict)


# Temporary placeholder until authentication supplies a real request identity.
def add_user_id(_, __, event_dict):
    event_dict["user_id"] = "12345"
    return event_dict


def set_process_id(_, __, event_dict):
    event_dict["process_id"] = os.getpid()
    return event_dict


def drop_metrics(_, __, event_dict):
    if event_dict.get("route") == "metrics":
        raise structlog.DropEvent
    return event_dict


def drop_health(_, __, event_dict):
    if event_dict.get("route") == "health":
        raise structlog.DropEvent
    return event_dict


level = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, level, logging.INFO)

shared_processors = [
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    set_process_id,
    add_user_id,
    drop_metrics,
    drop_health,
    redact_sensitive_data,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    capture_structlog_event,
    structlog.processors.UnicodeDecoder(),
]
if sys.stderr.isatty():
    processors = shared_processors + [structlog.dev.ConsoleRenderer()]
else:
    processors = shared_processors + [
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]


def enable_logfire_processor(processor) -> None:
    """Forward structlog events to Logfire before the console/JSON renderer."""
    if processor not in processors:
        processors.insert(-1, processor)
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
            processors=processors,
        )


structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    processors=processors,
)
