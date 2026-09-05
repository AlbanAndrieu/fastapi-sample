"""Tests for validated homelab provider settings."""

import pytest
from pydantic import ValidationError

from nabla.settings.homelab import (
    DEFAULT_TRUENAS_URL,
    TrueNASProviderSettings,
)


_TRUENAS_ENV = (
    "TRUENAS_URL",
    "TRUENAS_API_USERNAME",
    "TRUENAS_USERNAME",
    "TRUENAS_USER",
    "TRUENAS_API_KEY",
    "TRUENAS_MCP_API_KEY",
    "TRUENAS_API_VERIFY_SSL",
    "TRUENAS_VERIFY_SSL",
    "TRUENAS_WS_PATH",
)


def _clear_truenas_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _TRUENAS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_valid_without_credentials(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)

    settings = TrueNASProviderSettings()

    assert settings.url == DEFAULT_TRUENAS_URL
    assert settings.websocket_path == "/api/current"
    assert settings.verify_ssl is True
    assert settings.adapter_username == ""
    assert settings.canonical_api_key == ""
    assert settings.adapter_api_key == ""


def test_alias_precedence_and_adapter_key_fallback_are_explicit(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_USER", "legacy-user")
    monkeypatch.setenv("TRUENAS_USERNAME", "compat-user")
    monkeypatch.setenv("TRUENAS_API_USERNAME", "api-user")
    monkeypatch.setenv("TRUENAS_MCP_API_KEY", "7-mcp-secret")

    settings = TrueNASProviderSettings()

    assert settings.adapter_username == "api-user"
    assert settings.canonical_api_key == ""
    assert settings.adapter_api_key == "7-mcp-secret"
    assert settings.adapter_api_key_environment == "TRUENAS_MCP_API_KEY"
    assert "7-mcp-secret" not in repr(settings)


def test_canonical_api_key_wins_without_leaking_secret(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_API_KEY", "8-canonical-secret")
    monkeypatch.setenv("TRUENAS_MCP_API_KEY", "7-mcp-secret")

    settings = TrueNASProviderSettings()

    assert settings.canonical_api_key == "8-canonical-secret"
    assert settings.adapter_api_key == "8-canonical-secret"
    assert settings.adapter_api_key_environment == "TRUENAS_API_KEY"
    assert "8-canonical-secret" not in repr(settings)
    assert "7-mcp-secret" not in repr(settings)


def test_url_tls_and_websocket_path_are_normalized(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_URL", " https://172.17.0.24:7000/base ")
    monkeypatch.setenv("TRUENAS_API_VERIFY_SSL", "false")
    monkeypatch.setenv("TRUENAS_WS_PATH", "api/custom")

    settings = TrueNASProviderSettings()

    assert settings.url == "https://172.17.0.24:7000/base"
    assert settings.verify_ssl is False
    assert settings.websocket_path == "/api/custom"


def test_blank_values_keep_historical_defaults(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_URL", "   ")
    monkeypatch.setenv("TRUENAS_API_VERIFY_SSL", "   ")
    monkeypatch.setenv("TRUENAS_WS_PATH", "   ")

    settings = TrueNASProviderSettings()

    assert settings.url == DEFAULT_TRUENAS_URL
    assert settings.verify_ssl is False
    assert settings.websocket_path == "/api/current"


@pytest.mark.parametrize(
    "url",
    [
        "truenas.example.test:7000",
        "ftp://truenas.example.test",
        "https:///missing-host",
    ],
)
def test_invalid_urls_fail_during_settings_construction(monkeypatch, url: str) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_URL", url)

    with pytest.raises(ValidationError, match="TRUENAS_URL"):
        TrueNASProviderSettings()


def test_obsolete_verify_ssl_alias_remains_ignored(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_VERIFY_SSL", "false")

    assert TrueNASProviderSettings().verify_ssl is True
