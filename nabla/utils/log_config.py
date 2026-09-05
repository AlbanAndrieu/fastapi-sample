"""Configuration of project's loggers."""
# Here's the hierarchy of logging levels from lowest to highest severity
# DEBUG < INFO < WARNING < ERROR < CRITICAL

import json
import logging
import logging.config
import logging.handlers
import os
import re
import sys
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi.logger import logger as fastapi_logger
from gunicorn import glogging
from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware

from nabla.config_settings import get_settings
from nabla.utils.logger import logger
from nabla.utils.runtime_logs import attach_runtime_log_handler

_OTEL_LOG_FIELDS = ("otelTraceID", "otelSpanID", "otelServiceName")
_URL_PATTERN = re.compile(r"https?://[^\s\"']+")
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        return value
    if not hostname:
        return value
    safe_netloc = f"{hostname}{port}"
    query = "[REDACTED]" if parsed.query else ""
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, query, ""))


def sanitize_log_value(value: Any) -> Any:
    """Redact credentials and URL query strings from log payloads."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).casefold() in {"authorization", "cookie", "password", "secret", "token", "x-api-key"} else sanitize_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(sanitize_log_value(item) for item in value)
    if not isinstance(value, str):
        return value
    sanitized = _BEARER_PATTERN.sub(r"\1[REDACTED]", value)
    return _URL_PATTERN.sub(lambda match: _sanitize_url(match.group(0)), sanitized)


class SensitiveLogFilter(logging.Filter):
    """Remove common secrets before any configured handler emits a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_log_value(record.getMessage())
        record.args = ()
        for name in ("req", "res"):
            if hasattr(record, name):
                setattr(record, name, sanitize_log_value(getattr(record, name)))
        return True


class SafeFormatter(logging.Formatter):
    """Provide empty OpenTelemetry fields when instrumentation did not add them."""

    def format(self, record: logging.LogRecord) -> str:
        for field_name in _OTEL_LOG_FIELDS:
            if not hasattr(record, field_name):
                setattr(record, field_name, "")
        return super().format(record)


class JsonBaseFormatter(JsonFormatter):
    """Format the JSON logs into my style."""

    def __init__(
        self,
        additional_fields: Optional[set[str]] = None,
        additional_rename_fields: Optional[dict[str, str]] = None,
    ):
        """
        Initialize formatter.

        :param additional_fields: Besides message, level, and name, (default ones),
        you can add more from this list: https://docs.python.org/3/library/logging.html#logrecord-attributes
        :param additional_rename_fields: Besides the renaming of
        "name" -> "service_name", "levelname" -> "level",
        and "exc_info" -> "error_detail"
        you can add other fields to rename
        """
        super(JsonFormatter, self).__init__()

        base_fields = {"message", "levelname", "name"}
        base_rename_fields = {
            "name": "service_name",
            "levelname": "level",
        }

        if additional_fields is not None:
            base_fields.update(additional_fields)
        final_fields = ""
        for field in base_fields:
            final_fields += f"{{{field}}}"

        if additional_rename_fields is not None:
            base_rename_fields.update(additional_rename_fields)

        super().__init__(
            final_fields,
            style="{",
            rename_fields=base_rename_fields,
            timestamp=True,
        )

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """
        Add and update new fields of the logger.

        :param log_data: The dictionary storing the logs
        :param record: The LogRecord instance represents an event being logged.
        :param message_dict: A dictionary of messages
        :return: None
        """
        super().add_fields(log_data, record, message_dict)
        log_data["timestamp"] = log_data["timestamp"].strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )
        if "exc_info" in log_data:
            log_data["error_detail"] = log_data.pop("exc_info")

        # This type of messaged that comes from uvicorn.error is removed
        if "color_message" in log_data:
            log_data.pop("color_message")


def _json_log_record(record: logging.LogRecord) -> dict[str, Any]:
    """Return stable context shared by local and Gunicorn JSON logs."""
    return {
        "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
        "service_name": record.name,
        "level": record.levelname,
        "message": record.getMessage(),
    }


class JsonRequestFormatter(JsonBaseFormatter):
    def __init__(self):
        super(JsonBaseFormatter, self).__init__()

    def format(self, record):
        json_record = _json_log_record(record)
        if "req" in record.__dict__:
            json_record["req"] = record.__dict__["req"]
        if "res" in record.__dict__:
            json_record["res"] = record.__dict__["res"]
        if record.exc_info and record.levelno >= 40:
            json_record["err"] = self.formatException(record.exc_info)
        return json.dumps(json_record)


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        logger.info(
            "request_extra",
            extra={
                "req": {"method": request.method, "url": request.url.path},
                "res": {
                    "status_code": response.status_code,
                },
            },
        )
        return response


class JsonErrorFormatter(JsonBaseFormatter):
    def __init__(self):
        super(JsonBaseFormatter, self).__init__()

    def format(self, record):
        json_record = _json_log_record(record)
        if record.exc_info and record.levelno >= 40:
            json_record["err"] = self.formatException(record.exc_info)
        return json.dumps(json_record)


class JMGunicornLogger(glogging.Logger):
    def _set_handler(
        self,
        log: logging.Logger,
        output,
        fmt: logging.Formatter,
        stream=None,
    ) -> None:
        """
        Overrides Gunicorn Logger to add the JSON formatter

        :param log: The logger to update
        :param output: The output (I don't know what it means)
        :param fmt: The formatter to use (ignored in our case)
        :param stream: The stream to print (file, console, etc.)
        :return:
        """

        super()._set_handler(
            log=log,
            output=output,
            fmt=JsonRequestFormatter(),
            stream=stream,
        )


_QUIET_HEALTH_PATHS = frozenset({"/health", "/healthz", "/livez", "/readyz", "/sickz"})
_ACCESS_PATH_PATTERN = re.compile(r'"[A-Z]+ (?P<path>[^ ?"]+)')


def _access_log_path(record: logging.LogRecord) -> str | None:
    """Extract the request path from standard Uvicorn access-log records."""
    args = record.args
    if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
        return args[2].split("?", 1)[0]
    match = _ACCESS_PATH_PATTERN.search(record.getMessage())
    return match.group("path") if match else None


class HealthCheckFilter(logging.Filter):
    """Drop routine operational health access logs while keeping other requests."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _access_log_path(record) not in _QUIET_HEALTH_PATHS


class MetricsFilter(logging.Filter):
    """Drop routine metrics scrapes while keeping ordinary access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _access_log_path(record) != "/metrics"


def configure_library_log_levels() -> None:
    """Keep routine third-party polling chatter out of application INFO logs."""
    logging.getLogger("UnleashClient").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)


def setup_logging() -> None:
    """
    Configure the loggers of the project.
    """
    # Define the logging format
    log_level = logging.INFO

    # Need to setup loggers before importing other modules that may use loggers
    # Use whatever path you need to grab the log_config.json file
    with open(os.path.join(os.path.dirname(__file__), "log_config.json")) as f:
        logging.config.dictConfig(json.load(f))

    # Get root logger
    logger: logging.Logger = logging.getLogger()

    # Keep high-frequency operational probes out of access logs without hiding
    # ordinary application requests.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
    logging.getLogger("uvicorn.access").addFilter(MetricsFilter())

    # XXX: Taken from https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker/issues/19
    if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""):
        # When running with gunicorn the log handlers get suppressed instead of
        # passed along to the container manager. This forces the gunicorn handlers
        # to be used throughout the project.
        gunicorn_error_logger: logging.Logger = logging.getLogger("gunicorn.error")
        formatted_handlers = gunicorn_error_logger.handlers
        logger.handlers = formatted_handlers
        logger.setLevel(gunicorn_error_logger.level)
        fastapi_logger.handlers = formatted_handlers
        fastapi_logger.setLevel(gunicorn_error_logger.level)
    else:
        # Running locally through uvicorn

        log_level = logging.getLevelName(get_settings().log_level.upper())

        # update uvicorn access logger format
        # log_config = uvicorn.config.LOGGING_CONFIG
        # log_config["formatters"]["access"]["fmt"] = (
        #    "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s] - %(message)s"
        # )

        # ogging.getLogger("uvicorn.access").disabled = True

        # Stream Handler for console output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(JsonRequestFormatter())

        # Set console handler as the only handler for root logger
        logger.handlers = [console_handler]
        logger.setLevel(log_level)

    attach_runtime_log_handler(logger)
    sensitive_filter = SensitiveLogFilter()
    for configured_logger in (
        logger,
        logging.getLogger("gunicorn.error"),
        logging.getLogger("gunicorn.access"),
        logging.getLogger("uvicorn.access"),
    ):
        for handler in configured_logger.handlers:
            handler.addFilter(sensitive_filter)

    # Third-party polling libraries can emit high-volume INFO messages that add
    # no request-level diagnostic value. Preserve warnings/errors while keeping
    # the local console useful.
    configure_library_log_levels()
