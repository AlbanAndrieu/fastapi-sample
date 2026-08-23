"""Tests for the read-only TrueNAS 26 websocket API adapter."""

from unittest.mock import Mock

import pytest

from nabla.api.truenas_client import TrueNASReadOnlyAdapter, TrueNASSettings


class FakeClient:
    """Minimal official-client stand-in with deterministic read-only responses."""

    def __init__(self, *, uri: str, verify_ssl: bool) -> None:
        self.uri = uri
        self.verify_ssl = verify_ssl
        self.login = Mock()
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def login_with_api_key(self, username: str, api_key: str) -> None:
        self.login(username, api_key)

    def call(self, method: str, *params):
        self.calls.append(method)
        if method == "system.version":
            return "26.0.0-BETA.3"
        if method == "app.query":
            return [
                {"name": "open-webui", "state": "RUNNING", "upgrade_available": False},
                {"name": "litellm", "state": "CRASHED", "upgrade_available": True},
            ]
        raise AssertionError(f"unexpected TrueNAS method: {method}")


def test_settings_require_username_and_api_key(monkeypatch) -> None:
    for name in (
        "TRUENAS_API_USERNAME",
        "TRUENAS_USERNAME",
        "TRUENAS_API_KEY",
        "TRUENAS_MCP_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert TrueNASSettings.from_environment() is None


def test_settings_reuse_mcp_api_key(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_API_USERNAME", "readonly")
    monkeypatch.setenv("TRUENAS_MCP_API_KEY", "1-test-key")
    monkeypatch.delenv("TRUENAS_API_KEY", raising=False)
    monkeypatch.delenv("TRUENAS_URL", raising=False)

    settings = TrueNASSettings.from_environment()

    assert settings is not None
    assert settings.url == "https://172.17.0.24"
    assert settings.username == "readonly"
    assert settings.api_key == "1-test-key"
    assert settings.websocket_uri == "wss://172.17.0.24/api/current"
    assert settings.verify_ssl is True


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://truenas.example", "wss://truenas.example/api/current"),
        ("https://truenas.example/", "wss://truenas.example/api/current"),
        ("wss://truenas.example/api/current", "wss://truenas.example/api/current"),
        ("http://172.17.0.24", "ws://172.17.0.24/api/current"),
    ],
)
def test_websocket_uri_normalization(url: str, expected: str) -> None:
    settings = TrueNASSettings(url=url, username="readonly", api_key="key")

    assert settings.websocket_uri == expected


def test_health_snapshot_uses_system_version_and_app_query() -> None:
    clients: list[FakeClient] = []

    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    settings = TrueNASSettings(
        url="https://truenas.example",
        username="readonly",
        api_key="1-secret",
    )
    adapter = TrueNASReadOnlyAdapter(settings, client_factory=factory)

    snapshot = adapter.health_snapshot()

    assert snapshot == {
        "reachable": True,
        "version": "26.0.0-BETA.3",
        "apps": [
            {"name": "open-webui", "state": "RUNNING", "upgrade_available": False},
            {"name": "litellm", "state": "CRASHED", "upgrade_available": True},
        ],
    }
    assert clients[0].uri == "wss://truenas.example/api/current"
    assert clients[0].verify_ssl is True
    clients[0].login.assert_called_once_with("readonly", "1-secret")
    assert clients[0].calls == ["system.version", "app.query"]


def test_invalid_truenas_url_is_rejected() -> None:
    settings = TrueNASSettings(url="172.17.0.24", username="readonly", api_key="key")

    with pytest.raises(ValueError, match="TRUENAS_URL"):
        _ = settings.websocket_uri
