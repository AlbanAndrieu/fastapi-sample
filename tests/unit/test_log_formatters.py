"""Regression coverage for JSON logging during interpreter shutdown."""

import json
import logging

import pytest

from nabla.utils import log_config


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
