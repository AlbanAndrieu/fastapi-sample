"""Regression coverage for JSON logging during interpreter shutdown."""

import json
import logging

import pytest

from nabla.utils import log_config
from nabla.utils.logger import order_log_keys


def test_safe_formatter_supplies_missing_otel_fields() -> None:
    formatter = log_config.SafeFormatter(
        "%(levelname)s trace=%(otelTraceID)s span=%(otelSpanID)s service=%(otelServiceName)s %(message)s",
    )
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "ASGI failure",
        (),
        None,
    )

    rendered = formatter.format(record)

    assert rendered == "ERROR trace= span= service= ASGI failure"


@pytest.mark.parametrize(
    "formatter_type",
    [log_config.JsonRequestFormatter, log_config.JsonErrorFormatter],
)
def test_json_formatter_survives_logging_module_shutdown(
    monkeypatch,
    formatter_type,
) -> None:
    formatter = formatter_type()
    record = logging.LogRecord(
        "shutdown",
        logging.WARNING,
        __file__,
        1,
        "closing",
        (),
        None,
    )
    monkeypatch.setattr(log_config, "logging", None)

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "warning"


def test_json_request_formatter_keeps_logger_identity_and_timestamp() -> None:
    formatter = log_config.JsonRequestFormatter()
    record = logging.LogRecord(
        "UnleashClient",
        logging.WARNING,
        __file__,
        1,
        "feature fetch failed",
        (),
        None,
    )

    rendered = formatter.format(record)
    payload = json.loads(rendered)

    # Same schema and key order as structlog lines.
    assert list(payload) == ["timestamp", "level", "logger", "event"]
    assert payload["logger"] == "UnleashClient"
    assert payload["level"] == "warning"
    assert payload["event"] == "feature fetch failed"
    assert payload["timestamp"].endswith("Z")


def test_uvicorn_access_line_becomes_structured_without_query() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/x?token=secret", "1.1", 200),
        None,
    )

    payload = json.loads(log_config.JsonRequestFormatter().format(record))

    assert payload["event"] == "http_request"
    assert payload["http"] == {"client": "127.0.0.1:5000", "method": "GET", "path": "/api/x", "status": 200}


def test_structlog_lines_share_the_stdlib_key_order() -> None:
    ordered = order_log_keys({"user_id": "anonymous", "event": "e", "level": "info", "timestamp": "t", "logger": "nabla", "a": 1})

    assert list(ordered) == ["timestamp", "level", "logger", "event", "a", "user_id"]


def test_debug_level_keeps_transport_libraries_quiet() -> None:
    log_config.configure_library_log_levels()

    for name in ("httpcore", "passlib", "urllib3", "databases"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
