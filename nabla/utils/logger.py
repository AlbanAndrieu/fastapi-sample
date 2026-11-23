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
    r"(?P<value>[^\s,;}&]+)",
)
_CONNECTION_PASSWORD = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://[^:/\s]+:)(?P<password>[^@/\s]+)(?=@)")


def _redact_value(value):
    if isinstance(value, Mapping):
        return {key: _REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact_value(item) for key, item in value.items()}
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


# Public routes currently have no authenticated principal. Keep the field stable
# for downstream log consumers without inventing a user identity.
def add_user_id(_, __, event_dict):
    event_dict.setdefault("user_id", "anonymous")
    return event_dict


def set_process_id(_, __, event_dict):
    event_dict["process_id"] = os.getpid()
    return event_dict


def add_logger_name(_, __, event_dict):
    event_dict.setdefault("logger", "nabla")
    return event_dict


# One schema for structlog and stdlib JSON lines (see log_config._json_log_record).
LOG_KEY_ORDER = ("timestamp", "level", "logger", "event")


def order_log_keys(event: Mapping) -> dict:
    """Put the shared keys first, then context keys alphabetically."""
    head = {key: event[key] for key in LOG_KEY_ORDER if key in event}
    return head | {key: event[key] for key in sorted(event) if key not in head}


def order_keys(_, __, event_dict):
    return order_log_keys(event_dict)


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
    add_logger_name,
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
    processors = [*shared_processors, structlog.dev.ConsoleRenderer()]
else:
    processors = [
        *shared_processors,
        structlog.processors.dict_tracebacks,
        order_keys,
        structlog.processors.JSONRenderer(ensure_ascii=False),
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
