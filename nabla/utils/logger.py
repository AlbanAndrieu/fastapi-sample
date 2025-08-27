import logging
import os
import sys

import structlog

logger = structlog.get_logger()


# Custom processor to add user_id to log entries
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
LOG_LEVEL = getattr(logging, level)


shared_processors = [
    # Processors that have nothing to do with output,
    # e.g., add timestamps or log level names.
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    set_process_id,
    add_user_id,
    drop_metrics,
    drop_health,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]
if sys.stderr.isatty():
    # Pretty printing when we run in a terminal session.
    # Automatically prints pretty tracebacks when "rich" is installed
    processors = shared_processors + [  # noqa
        structlog.dev.ConsoleRenderer(),
    ]
else:
    # Print JSON when we run, e.g., in a Docker container.
    # Also print structured tracebacks.
    processors = shared_processors + [  # noqa
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]

# Configure structlog to output in JSON format
# See https://betterstack.com/community/guides/logging/structlog/
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    processors=processors,
)
