"""Tests for typed observability settings."""

import inspect

import pytest
from pydantic import ValidationError

from nabla.api import observability_health
from nabla.settings.observability import LogfireProbeSettings, LogfireSettings
from nabla.utils import logfire_config, sentry_config


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("", True),
        ("unexpected", True),
    ],
)
def test_logfire_settings_preserve_enabled_parsing(
    monkeypatch,
    value: str,
    expected: bool,
) -> None:
    monkeypatch.setenv("LOGFIRE_ENABLED", value)

    assert LogfireSettings().instrumentation_enabled is expected


def test_logfire_probe_preserves_legacy_enable_fallback(monkeypatch) -> None:
    monkeypatch.delenv("LOGFIRE_ENABLED", raising=False)
    monkeypatch.setenv("LOGFIRE_ENABLE", "false")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")

    assert LogfireSettings().instrumentation_enabled is True
    assert LogfireProbeSettings().probe_enabled is False


def test_logfire_probe_canonical_enable_wins_over_legacy(monkeypatch) -> None:
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_ENABLE", "false")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")

    assert LogfireProbeSettings().probe_enabled is True


def test_logfire_token_is_trimmed_and_secret(monkeypatch) -> None:
    expected_value = "test-token"
    monkeypatch.setenv("LOGFIRE_TOKEN", f"  {expected_value}  ")

    settings = LogfireSettings()

    assert settings.token == expected_value
    assert expected_value not in repr(settings.logfire_token)


def test_logfire_probe_validates_https_base_url(monkeypatch) -> None:
    monkeypatch.setenv("LOGFIRE_BASE_URL", "http://logfire.example")

    with pytest.raises(ValidationError, match="LOGFIRE_BASE_URL"):
        LogfireProbeSettings()


def test_logfire_settings_from_mapping_ignore_process_logfire_values(monkeypatch) -> None:
    expected_value = "mapped-token"
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_TOKEN", "process-token")

    settings = LogfireSettings.from_mapping(
        {
            "LOGFIRE_ENABLED": "false",
            "LOGFIRE_TOKEN": f"  {expected_value}  ",
        },
    )

    assert settings.instrumentation_enabled is False
    assert settings.instrumentation_active is False
    assert settings.token == expected_value


def test_runtime_modules_do_not_reparse_migrated_logfire_environment() -> None:
    for module in (logfire_config, observability_health, sentry_config):
        source = inspect.getsource(module)
        assert "os.getenv" not in source
    assert "LOGFIRE_ENABLED" not in inspect.getsource(sentry_config)
    assert "LOGFIRE_TOKEN" not in inspect.getsource(sentry_config)
