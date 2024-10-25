"""Configuration of project's loggers."""
# Here's the hierarchy of logging levels from lowest to highest severity
# DEBUG < INFO < WARNING < ERROR < CRITICAL

import json
import logging
import logging.handlers
import os
import sys
from typing import Any, Optional

from fastapi.logger import logger as fastapi_logger
from gunicorn import glogging
from pythonjsonlogger.jsonlogger import JsonFormatter


class _JMJsonFormatter(JsonFormatter):
    def __init__(self):
        super(JsonFormatter, self).__init__()

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
        return json.dumps(json_record)


class _JMLoggerFormatter(JsonFormatter):
    """Format the JSON logs."""

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
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """
        Add and update new fields of the logger.

        :param log_record: The dictionary storing the logs
        :param record: The LogRecord instance represents an event being logged.
        :param message_dict: A dictionary of messages
        :return: None
        """
        super().add_fields(
            log_record=log_record, record=record, message_dict=message_dict
        )
        log_record["timestamp"] = log_record["timestamp"].strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        if "exc_info" in log_record:
            log_record["error_detail"] = log_record.pop("exc_info")

        # This type of messaged that comes from uvicorn.error is removed
        if "color_message" in log_record:
            log_record.pop("color_message")


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
            log=log, output=output, fmt=_JMLoggerFormatter(), stream=stream
        )


def setup_logging() -> None:
    """
    Configure the loggers of the project.
    """
    # Define the logging format
    log_level = logging.INFO

    # Get root logger
    logger: logging.Logger = logging.getLogger()

    # XXX: Taken from https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker/issues/19
    if "gunicorn" in os.environ.get("SERVER_SOFTWARE", ""):
        # When running with gunicorn the log handlers get suppressed instead of
        # passed along to the container manager. This forces the gunicorn handlers
        # to be used throughout the project.
        gunicorn_error_logger: logging.Logger = logging.getLogger("gunicorn.error")
        formatted_handlers = gunicorn_error_logger.handlers
        seen_logger: set[str] = set()
        for logger_name in [
            *logging.root.manager.loggerDict.keys(),
            "gunicorn",
            "gunicorn.access",
            "uvicorn",
            "uvicorn.access",
            "uvicorn.error",
        ]:
            if logger_name in seen_logger:
                continue
            seen_logger.add(logger_name)
            local_logger = logging.getLogger(logger_name)
            local_logger.handlers = formatted_handlers
            local_logger.setLevel(log_level)
        logger.handlers = formatted_handlers
        fastapi_logger.handlers = formatted_handlers
        fastapi_logger.setLevel(log_level)

    else:
        # Running locally through uvicorn

        # Stream Handler for console output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        # console_handler.setFormatter(JsonFormatter())
        console_handler.setFormatter(_JMLoggerFormatter())

        # Add the handlers to the root logger
        logger.addHandler(console_handler)

    # Pass on logging levels for root
    logger.setLevel(log_level)
