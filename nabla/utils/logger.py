import logging
import os

import structlog

logger = structlog.get_logger()


# Custom processor to add user_id to log entries
def add_user_id(_, __, event_dict):
    event_dict["user_id"] = "12345"
    return event_dict


def set_process_id(_, __, event_dict):
    event_dict["process_id"] = os.getpid()
    return event_dict


level = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, level)

# Configure structlog to output in JSON format
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        set_process_id,
        add_user_id,
        structlog.processors.JSONRenderer(),
        # structlog.dev.ConsoleRenderer(),
    ],
)
