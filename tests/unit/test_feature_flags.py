"""Regression tests for lazy, opt-in feature-flag clients."""

from unittest.mock import Mock

import pytest

from nabla import feature_flags
from nabla.settings.feature_flags import StatsigSettings, UnleashSettings


@pytest.mark.parametrize("value", [None, "", "XXX", "change-me"])
def test_unleash_placeholder_credentials_are_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("UNLEASH_INSTANCE_ID", raising=False)
    else:
        monkeypatch.setenv("UNLEASH_INSTANCE_ID", value)

    assert feature_flags.unleash_is_configured() is False


def test_unleash_real_instance_id_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNLEASH_INSTANCE_ID", "gitlab-client-token")

    assert feature_flags.unleash_is_configured() is True


def test_unleash_client_fails_before_network_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock()
    monkeypatch.setenv("UNLEASH_INSTANCE_ID", "XXX")
    monkeypatch.setattr(feature_flags, "UnleashClient", constructor)
    feature_flags.get_unleash_client.cache_clear()

    with pytest.raises(RuntimeError, match="UNLEASH_INSTANCE_ID"):
        feature_flags.get_unleash_client()

    constructor.assert_not_called()
    feature_flags.get_unleash_client.cache_clear()


def test_unleash_configuration_ignores_import_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        feature_flags,
        "UNLEASH_INSTANCE_ID",
        "legacy-imported-instance-id",
    )
    monkeypatch.delenv("UNLEASH_INSTANCE_ID", raising=False)

    assert feature_flags.unleash_is_configured() is False


def test_unleash_settings_from_mapping_are_hermetic() -> None:
    settings = UnleashSettings.from_mapping({})

    assert settings.configured is False
    assert settings.instance_id == ""
    assert settings.api_url == ("https://gitlab.com/api/v4/feature_flags/unleash/46788175")
    assert settings.unleash_request_timeout == 45


@pytest.mark.parametrize("value", [None, "", "XXX", "change-me"])
def test_statsig_placeholder_credentials_are_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("STATSIG_API_KEY", raising=False)
    else:
        monkeypatch.setenv("STATSIG_API_KEY", value)

    assert feature_flags.get_statsig_settings().configured is False


def test_statsig_real_api_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STATSIG_API_KEY", "statsig-server-key")

    assert feature_flags.get_statsig_settings().configured is True


def test_statsig_client_fails_before_network_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock()
    monkeypatch.setenv("STATSIG_API_KEY", "XXX")
    monkeypatch.setattr(feature_flags, "Statsig", constructor)
    feature_flags.get_statsig_client.cache_clear()

    with pytest.raises(RuntimeError, match="STATSIG_API_KEY"):
        feature_flags.get_statsig_client()

    constructor.assert_not_called()
    feature_flags.get_statsig_client.cache_clear()


def test_statsig_configuration_ignores_import_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        feature_flags,
        "STATSIG_API_KEY",
        "legacy-imported-api-key",
    )
    monkeypatch.delenv("STATSIG_API_KEY", raising=False)

    assert feature_flags.get_statsig_settings().configured is False


def test_statsig_settings_from_mapping_are_hermetic() -> None:
    settings = StatsigSettings.from_mapping({})

    assert settings.configured is False
    assert settings.api_key == ""
    assert settings.statsig_environment == "development"
