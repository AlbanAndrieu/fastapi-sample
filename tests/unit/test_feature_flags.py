"""Regression tests for lazy, opt-in feature-flag clients."""

from unittest.mock import Mock

import pytest

from nabla import feature_flags


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
