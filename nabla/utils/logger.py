import json
import logging
from logging import Formatter

import structlog

logger = structlog.get_logger()
# logger = logging.root


# Custom processor to add user_id to log entries
def add_user_id(_, __, event_dict):
    event_dict["user_id"] = "12345"
    return event_dict


# Configure structlog to output in JSON format
structlog.configure(processors=[add_user_id, structlog.processors.JSONRenderer()])


class JsonFormatter(Formatter):
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


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers = [handler]
# logger.setLevel(logging.DEBUG)

# Remove /credentials/health from application server logs
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

logging.getLogger("uvicorn.access").disabled = True
