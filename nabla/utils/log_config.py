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


class SafeFormatter(logging.Formatter):
    """Formatter that replaces missing keys with empty string or N/A."""

    def format(self, record):
        default_keys = {
            "otelTraceID": "",
            "otelSpanID": "",
            "otelServiceName": "",
        }
        for k, v in default_keys.items():
            if k not in record.__dict__:
                record.__dict__[k] = v
        return super().format(record)


class JsonBaseFormatter(JsonFormatter):
    def __init__(
        self,
        additional_fields: Optional[set[str]] = None,
        additional_rename_fields: Optional[dict[str, str]] = None,
    ):
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
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(
            log_record=log_record,
            record=record,
            message_dict=message_dict,
        )
        log_record["timestamp"] = log_record["timestamp"].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if "exc_info" in log_record:
            log_record["error_detail"] = log_record.pop("exc_info")
        if "color_message" in log_record:
            log_record.pop("color_message")


class JsonRequestFormatter(JsonBaseFormatter):
    def __init__(self):
        super(JsonBaseFormatter, self).__init__()

    def format(self, record):
        json_record = {}
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


class JsonErrorFormatter(JsonBaseFormatter):
    def __init__(self):
        super(JsonBaseFormatter, self).__init__()

    def format(self, record):
        json_record = {}
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


def setup_logging() -> None:
    log_level = logging.INFO
    with open(os.path.join(os.path.dirname(__file__), "log_config.json")) as f:
        logging.config.dictConfig(json.load(f))
    logger: logging.Logger = logging.getLogger()
    # Les lignes suivantes étaient incorrectes et provoquaient un TypeError.
    # logging.getLogger("uvicorn.access").addFilter(JsonRequestFormatter())
    # logging.getLogger("uvicorn.access").addFilter(JsonErrorFormatter())
