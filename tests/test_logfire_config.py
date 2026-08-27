import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nabla.utils.logfire_config import configure_logfire


@pytest.mark.parametrize("token", [None, "", "   "])
def test_logfire_is_disabled_without_token(monkeypatch, token):
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    if token is None:
        monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOGFIRE_TOKEN", token)
    load_sdk = MagicMock()
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", load_sdk)

    assert not configure_logfire(MagicMock(), service_name="test", service_version="1")
    load_sdk.assert_not_called()


def test_logfire_is_disabled_explicitly_during_pytest(monkeypatch):
    monkeypatch.setenv("LOGFIRE_ENABLED", "false")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
    load_sdk = MagicMock()
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", load_sdk)

    assert not configure_logfire(MagicMock(), service_name="test", service_version="1")
    load_sdk.assert_not_called()


def test_logfire_uses_project_token_without_forcing_endpoint(monkeypatch):
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
    monkeypatch.setenv("LOGFIRE_ENVIRONMENT", "test")
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False)
    configure = MagicMock()
    instrument = MagicMock()
    instrument_system_metrics = MagicMock()
    structlog_processor = object()
    logfire = SimpleNamespace(
        StructlogProcessor=MagicMock(return_value=structlog_processor),
        configure=configure,
        instrument_fastapi=instrument,
        instrument_system_metrics=instrument_system_metrics,
    )
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", MagicMock(return_value=logfire))
    enable_processor = MagicMock()
    monkeypatch.setattr("nabla.utils.logfire_config.enable_logfire_processor", enable_processor)

    app = MagicMock()
    assert configure_logfire(app, service_name="fastapi-sample", service_version="1")

    configure.assert_called_once()
    options = configure.call_args.kwargs
    assert options["token"] == os.environ["LOGFIRE_TOKEN"]
    assert options["send_to_logfire"] is True
    assert options["service_name"] == "fastapi-sample"
    assert options["service_version"] == "1"
    assert options["environment"] == "test"
    assert "advanced" not in options
    instrument_system_metrics.assert_called_once_with()
    instrument.assert_called_once()
    enable_processor.assert_called_once_with(structlog_processor)
    assert instrument.call_args.args == (app,)
    instrumentation_options = instrument.call_args.kwargs
    assert instrumentation_options["capture_headers"] is False
    assert "health" in instrumentation_options["excluded_urls"]
    assert "openapi" in instrumentation_options["excluded_urls"]
    assert "v1/mcp" in instrumentation_options["excluded_urls"]
    assert (
        instrumentation_options["request_attributes_mapper"](
            MagicMock(),
            {"values": {"field": object()}},
        )
        == {}
    )
    assert os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"


def test_logfire_preserves_explicit_genai_content_setting(monkeypatch):
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    logfire = SimpleNamespace(
        StructlogProcessor=MagicMock(return_value=object()),
        configure=MagicMock(),
        instrument_fastapi=MagicMock(),
        instrument_system_metrics=MagicMock(),
    )
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", MagicMock(return_value=logfire))
    monkeypatch.setattr("nabla.utils.logfire_config.enable_logfire_processor", MagicMock())

    assert configure_logfire(MagicMock(), service_name="test", service_version="1")
    assert os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "true"


def test_logfire_failure_does_not_block_startup(monkeypatch):
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_TOKEN", "invalid-token")
    logfire = SimpleNamespace(
        StructlogProcessor=MagicMock(),
        configure=MagicMock(side_effect=RuntimeError("unavailable")),
    )
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", MagicMock(return_value=logfire))

    assert not configure_logfire(MagicMock(), service_name="test", service_version="1")
