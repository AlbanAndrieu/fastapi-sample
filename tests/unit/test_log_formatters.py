"""Regression coverage for JSON logging during interpreter shutdown."""

import json
import logging

import pytest

from nabla.utils import log_config


def test_safe_formatter_supplies_missing_otel_fields() -> None:
    formatter = log_config.SafeFormatter(
        "%(levelname)s trace=%(otelTraceID)s span=%(otelSpanID)s "
        "service=%(otelServiceName)s %(message)s"
    )
    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, __file__, 1, "ASGI failure", (), None
    )

    rendered = formatter.format(record)

    assert rendered == "ERROR trace= span= service= ASGI failure"


@pytest.mark.parametrize(
    "formatter_type",
    [log_config.JsonRequestFormatter, log_config.JsonErrorFormatter],
)
def test_json_formatter_survives_logging_module_shutdown(
    monkeypatch, formatter_type
) -> None:
    formatter = formatter_type()
    record = logging.LogRecord(
        "shutdown", logging.WARNING, __file__, 1, "closing", (), None
    )
    monkeypatch.setattr(log_config, "logging", None)

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "WARNING"



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

    payload = json.loads(formatter.format(record))

    assert payload["service_name"] == "UnleashClient"
    assert payload["level"] == "WARNING"
    assert payload["message"] == "feature fetch failed"
    assert payload["timestamp"].endswith("Z")
