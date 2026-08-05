"""Tests for local-first, Logfire-aware Sentry configuration."""

from unittest.mock import Mock

import sentry_sdk

from nabla.utils import sentry_config


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
