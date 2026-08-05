import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nabla.utils.logfire_config import LOGFIRE_BASE_URL, configure_logfire


@pytest.mark.parametrize("token", [None, "", "   "])
def test_logfire_is_disabled_without_token(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOGFIRE_TOKEN", token)
    load_sdk = MagicMock()
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", load_sdk)

    assert not configure_logfire(MagicMock(), service_name="test", service_version="1")
    load_sdk.assert_not_called()


def test_logfire_uses_eu_project_token_without_request_data(monkeypatch):
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")
    monkeypatch.setenv("LOGFIRE_ENVIRONMENT", "test")
    configure = MagicMock()
    instrument = MagicMock()
    logfire = SimpleNamespace(
        AdvancedOptions=SimpleNamespace,
        configure=configure,
        instrument_fastapi=instrument,
    )
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", MagicMock(return_value=logfire))

    app = MagicMock()
    assert configure_logfire(app, service_name="fastapi-sample", service_version="1")

    configure.assert_called_once()
    options = configure.call_args.kwargs
    assert options["token"] == os.environ["LOGFIRE_TOKEN"]
    assert options["send_to_logfire"] is True
    assert options["service_name"] == "fastapi-sample"
    assert options["environment"] == "test"
    assert options["advanced"].base_url == LOGFIRE_BASE_URL
    instrument.assert_called_once()
    assert instrument.call_args.args == (app,)
    instrumentation_options = instrument.call_args.kwargs
    assert instrumentation_options["capture_headers"] is False
    assert "health" in instrumentation_options["excluded_urls"]
    assert (
        instrumentation_options["request_attributes_mapper"](
            MagicMock(),
            {"values": {"field": object()}},
        )
        is None
    )


def test_logfire_failure_does_not_block_startup(monkeypatch):
    monkeypatch.setenv("LOGFIRE_TOKEN", "invalid-token")
    logfire = SimpleNamespace(
        AdvancedOptions=MagicMock(),
        configure=MagicMock(side_effect=RuntimeError("unavailable")),
    )
    monkeypatch.setattr("nabla.utils.logfire_config.import_module", MagicMock(return_value=logfire))

    assert not configure_logfire(MagicMock(), service_name="test", service_version="1")
