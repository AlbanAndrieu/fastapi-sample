"""Configuration of project's loggers."""
# Here's the hierarchy of logging levels from lowest to highest severity
# DEBUG < INFO < WARNING < ERROR < CRITICAL

import json
import logging
import logging.config
import logging.handlers
import os
import sys
from typing import Any, Optional

from fastapi.logger import logger as fastapi_logger
from gunicorn import glogging
from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware

from nabla.config_settings import get_settings
from nabla.utils.logger import logger


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


class JsonRequestFormatter(JsonBaseFormatter):
    def __init__(self):
        super(JsonBaseFormatter, self).__init__()

    def format(self, record):
        json_record = {}
        # json_record["data"] = record.getMessage()
        json_record["message"] = record.getMessage()
        if "req" in record.__dict__:
            json_record["req"] = record.__dict__["req"]
        if "res" in record.__dict__:
            json_record["res"] = record.__dict__["res"]
        if record.levelno == logging.ERROR and record.exc_info:
            json_record["err"] = self.formatException(record.exc_info)
        if "levelname" in record.__dict__:
            json_record["level"] = record.__dict__["levelname"]
        return json.dumps(json_record)


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        logger.info(
            "request_extra",
            extra={
                "req": {"method": request.method, "url": str(request.url)},
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
        json_record = {}
        # json_record["data"] = record.getMessage()
        if record.levelno == logging.ERROR and record.exc_info:
            json_record["err"] = self.formatException(record.exc_info)
        if "levelname" in record.__dict__:
            json_record["level"] = record.__dict__["levelname"]
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


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


class MetricsFilter(logging.Filter):
    # Uvicorn endpoint access log filter
    def filter(self, record: logging.LogRecord) -> bool:
        # return record.getMessage().find("GET /metrics") == -1
        return record.getMessage().find("metrics") != -1


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

    # Remove /credentials/health from application server logs
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
