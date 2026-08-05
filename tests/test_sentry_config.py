"""Tests for local-first, Logfire-aware Sentry configuration."""

from unittest.mock import Mock

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.mcp import MCPIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from nabla.utils import sentry_config


def test_uses_default_cloud_sentry_dsn(monkeypatch) -> None:
    monkeypatch.setattr(sentry_config, "sentry_dsn_is_reachable", lambda _dsn: False)

    assert sentry_config.select_sentry_dsn({}) == (
        sentry_config.DEFAULT_SENTRY_DSN,
        "cloud",
    )


def test_selects_reachable_local_sentry(monkeypatch) -> None:
    monkeypatch.setattr(sentry_config, "sentry_dsn_is_reachable", lambda _dsn: True)

    dsn, target = sentry_config.select_sentry_dsn(
        {"SENTRY_DSN": "https://public@example.ingest.sentry.io/42"},
    )

    assert dsn == "https://public@localhost:9000/42"
    assert target == "local"


def test_falls_back_to_cloud_sentry(monkeypatch) -> None:
    monkeypatch.setattr(sentry_config, "sentry_dsn_is_reachable", lambda _dsn: False)
    cloud_dsn = "https://public@example.ingest.sentry.io/42"

    assert sentry_config.select_sentry_dsn({"SENTRY_DSN": cloud_dsn}) == (
        cloud_dsn,
        "cloud",
    )


def test_logfire_disables_sentry_logs_traces_and_profiles(monkeypatch) -> None:
    init = Mock()
    monkeypatch.setattr(sentry_config, "select_sentry_dsn", lambda _env: ("https://public@example.com/1", "cloud"))
    monkeypatch.setattr(sentry_config, "_integrations", lambda **_kwargs: [])
    monkeypatch.setattr(sentry_sdk, "init", init)

    assert sentry_config.configure_sentry(
        {"SENTRY_DSN": "https://public@example.com/1", "LOGFIRE_TOKEN": "token"},
    )

    kwargs = init.call_args.kwargs
    assert kwargs["enable_logs"] is False
    assert kwargs["traces_sample_rate"] is None
    assert kwargs["profiles_sample_rate"] == 0.0
    assert kwargs["send_default_pii"] is False


def test_sentry_enables_logs_without_logfire(monkeypatch) -> None:
    init = Mock()
    monkeypatch.setattr(sentry_config, "select_sentry_dsn", lambda _env: ("https://public@example.com/1", "cloud"))
    monkeypatch.setattr(sentry_config, "_integrations", lambda **_kwargs: [])
    monkeypatch.setattr(sentry_sdk, "init", init)

    assert sentry_config.configure_sentry({"SENTRY_DSN": "https://public@example.com/1"})

    kwargs = init.call_args.kwargs
    assert kwargs["enable_logs"] is True
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["profiles_sample_rate"] == 0.0
    assert kwargs["send_default_pii"] is False
    assert kwargs["sample_rate"] == 1.0
    assert kwargs["max_breadcrumbs"] == 50
    assert kwargs["shutdown_timeout"] == 2.0


def test_scrubs_sensitive_fields() -> None:
    event = {
        "request": {
            "headers": {"Authorization": "Bearer secret", "accept": "application/json"},
            "cookies": {"token": "secret"},
        },
    }

    scrubbed = sentry_config._before_send(event, {})

    assert scrubbed["request"]["headers"]["Authorization"] == sentry_config._FILTERED_VALUE
    assert scrubbed["request"]["cookies"]["token"] == sentry_config._FILTERED_VALUE
    assert event["request"]["headers"]["Authorization"] == "Bearer secret"


def test_filters_technical_transactions() -> None:
    assert (
        sentry_config._before_send_transaction(
            {"request": {"url": "https://example.test/metrics?format=openmetrics"}},
            {},
        )
        is None
    )
    assert (
        sentry_config._before_send_transaction(
            {"transaction": "/healthz"},
            {},
        )
        is None
    )
    assert (
        sentry_config._before_send_transaction(
            {"request": {"url": "https://example.test/api"}},
            {},
        )
        is not None
    )


def test_core_integrations_are_explicit() -> None:
    integrations = sentry_config._integrations(include_logging=False)

    assert any(isinstance(item, FastApiIntegration) for item in integrations)
    assert any(isinstance(item, SqlalchemyIntegration) for item in integrations)
    assert any(isinstance(item, MCPIntegration) for item in integrations)
