"""Tests for the read-only TrueNAS 26 WebSocket API adapter."""

from unittest.mock import Mock

import pytest

from nabla.integrations.truenas_client import (
    TrueNASReadOnlyAdapter,
    TrueNASSettings,
    _truenas_failure_stage,
    _websocket_proxy_route,
    truenas_host_port,
)


class FakeClient:
    """Minimal official-client stand-in with deterministic read-only responses."""

    def __init__(self, *, uri: str, call_timeout: float, verify_ssl: bool) -> None:
        self.uri = uri
        self.call_timeout = call_timeout
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
        "TRUENAS_USER",
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
    assert settings.url == "https://truenas.albandrieu.com:7000"
    assert settings.username == "readonly"
    assert settings.api_key == "1-test-key"
    assert settings.websocket_uri == ("wss://truenas.albandrieu.com:7000/api/current")
    assert settings.verify_ssl is True
    assert settings.call_timeout == 5.0


def test_settings_use_canonical_api_verify_ssl(monkeypatch) -> None:
    monkeypatch.delenv("TRUENAS_API_USERNAME", raising=False)
    monkeypatch.delenv("TRUENAS_USERNAME", raising=False)
    monkeypatch.setenv("TRUENAS_USER", "legacy-user")
    monkeypatch.setenv("TRUENAS_API_KEY", "1-test-key")
    monkeypatch.setenv("TRUENAS_API_VERIFY_SSL", "false")
    monkeypatch.setenv("TRUENAS_VERIFY_SSL", "true")

    settings = TrueNASSettings.from_environment()

    assert settings is not None
    assert settings.username == "legacy-user"
    assert settings.verify_ssl is False


def test_legacy_verify_ssl_alias_is_not_used(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_API_USERNAME", "readonly")
    monkeypatch.setenv("TRUENAS_API_KEY", "1-test-key")
    monkeypatch.delenv("TRUENAS_API_VERIFY_SSL", raising=False)
    monkeypatch.setenv("TRUENAS_VERIFY_SSL", "false")

    settings = TrueNASSettings.from_environment()

    assert settings is not None
    assert settings.verify_ssl is True


def test_settings_accept_custom_websocket_path(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_API_USERNAME", "readonly")
    monkeypatch.setenv("TRUENAS_API_KEY", "1-test-key")
    monkeypatch.setenv("TRUENAS_URL", "https://truenas.example/base")
    monkeypatch.setenv("TRUENAS_WS_PATH", "/api/custom")

    settings = TrueNASSettings.from_environment()

    assert settings is not None
    assert settings.websocket_path == "/api/custom"
    assert settings.websocket_uri == "wss://truenas.example/base/api/custom"


def test_local_url_override_drives_api_and_health_target(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_API_USERNAME", "readonly")
    monkeypatch.setenv("TRUENAS_API_KEY", "1-test-key")
    monkeypatch.setenv("TRUENAS_URL", "https://172.17.0.24:7000")

    settings = TrueNASSettings.from_environment()

    assert settings is not None
    assert settings.websocket_uri == "wss://172.17.0.24:7000/api/current"
    assert truenas_host_port() == ("172.17.0.24", 7000)


def test_websocket_proxy_route_is_direct_without_https_proxy(monkeypatch) -> None:
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    assert _websocket_proxy_route("truenas.albandrieu.com") == "direct"


def test_websocket_proxy_route_detects_proxy_candidate(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    assert _websocket_proxy_route("truenas.albandrieu.com") == "proxy_candidate"


def test_failure_stage_classifies_client_websocket_close() -> None:
    exc = RuntimeError("WebSocket connection closed with code=None, reason=None")

    assert _truenas_failure_stage(exc) == "websocket"


def test_failure_stage_classifies_truenas_source_allowlist_denial() -> None:
    exc = RuntimeError(
        "WebSocket connection closed with code=1008, "
        "reason='You are not allowed to access this resource'"
    )

    assert _truenas_failure_stage(exc) == "source_allowlist"


def test_websocket_proxy_route_honors_no_proxy_without_logging_value(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", ".albandrieu.com,localhost")
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    assert _websocket_proxy_route("truenas.albandrieu.com") == "bypass"


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
    assert clients[0].call_timeout == 5.0
    assert clients[0].verify_ssl is True
    clients[0].login.assert_called_once_with("readonly", "1-secret")
    assert clients[0].calls == ["system.version", "app.query"]


def test_custom_call_timeout_is_forwarded_to_official_client() -> None:
    clients: list[FakeClient] = []

    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    settings = TrueNASSettings(
        url="https://truenas.example",
        username="readonly",
        api_key="1-secret",
        call_timeout=2.5,
    )
    adapter = TrueNASReadOnlyAdapter(settings, client_factory=factory)

    adapter.system_version()

    assert clients[0].call_timeout == 2.5


def test_invalid_truenas_url_is_rejected() -> None:
    settings = TrueNASSettings(url="172.17.0.24", username="readonly", api_key="key")

    with pytest.raises(ValueError, match="TRUENAS_URL"):
        _ = settings.websocket_uri
