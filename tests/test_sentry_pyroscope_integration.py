"""Validate Sentry tracing and Pyroscope profiling can coexist."""

from unittest.mock import Mock

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

from nabla.utils import pyroscope_config, sentry_config


def test_sentry_tracing_and_pyroscope_profiling_can_run_together(monkeypatch) -> None:
    sentry_init = Mock()
    pyroscope_configure = Mock()

    monkeypatch.setattr(
        sentry_config,
        "select_sentry_dsn",
        lambda _env: ("http://public@172.17.0.24:9005/2", "local"),
    )
    monkeypatch.setattr(sentry_sdk, "init", sentry_init)
    monkeypatch.setattr(
        pyroscope_config.pyroscope,
        "configure",
        pyroscope_configure,
    )

    sentry_enabled = sentry_config.configure_sentry(
        {
            "APP_NAME": "fastapi-sample",
            "LOGFIRE_ENABLED": "false",
            "SENTRY_ENABLED": "true",
            "SENTRY_ENVIRONMENT": "homelab",
            "SENTRY_TRACES_SAMPLE_RATE": "1.0",
        },
    )
    pyroscope_enabled = pyroscope_config.start_pyroscope(
        enabled=True,
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
    )

    assert sentry_enabled is True
    assert pyroscope_enabled is True

    sentry_kwargs = sentry_init.call_args.kwargs
    assert sentry_kwargs["enable_logs"] is True
    assert sentry_kwargs["traces_sample_rate"] == 1.0
    assert sentry_kwargs["environment"] == "homelab"
    assert sentry_kwargs["server_name"] == "fastapi-sample"

    fastapi_integration = next(integration for integration in sentry_kwargs["integrations"] if isinstance(integration, FastApiIntegration))
    assert fastapi_integration.transaction_style == "url"

    pyroscope_configure.assert_called_once_with(
        application_name="fastapi-sample",
        server_address="http://172.17.0.24:4040",
        sample_rate=100,
        enable_logging=False,
    )
