"""Tests for network-stage diagnostics used by TrueNAS probes."""

import inspect
import logging
import ssl

import httpx
import pytest

from nabla.api.health_checks import _http_probe_error_kind, probe_https_get_reachable
from nabla.api.homelab_health import truenas_http_verify_ssl
from nabla.integrations.truenas_client import (
    TrueNASReadOnlyAdapter,
    TrueNASSettings,
    _truenas_failure_stage,
)


def test_http_probe_classifies_dns_failure() -> None:
    exc = httpx.ConnectError("Name or service not known")

    assert _http_probe_error_kind(exc) == "dns_error"


def test_http_probe_classifies_tls_failure() -> None:
    exc = httpx.ConnectError(str(ssl.SSLError("certificate verify failed")))

    assert _http_probe_error_kind(exc) == "tls_error"


def test_http_probe_classifies_connect_timeout() -> None:
    exc = httpx.ConnectTimeout("connection timed out")

    assert _http_probe_error_kind(exc) == "connect_timeout"


def test_http_probe_keeps_probe_name_contract() -> None:
    """Prevent the /healthz orchestration/runtime signature drift that caused HTTP 500."""
    signature = inspect.signature(probe_https_get_reachable)

    assert "probe_name" in signature.parameters
    assert signature.parameters["probe_name"].kind is inspect.Parameter.KEYWORD_ONLY


def test_truenas_http_verify_ssl_defaults_to_true(monkeypatch) -> None:
    monkeypatch.delenv("TRUENAS_API_VERIFY_SSL", raising=False)
    monkeypatch.delenv("TRUENAS_VERIFY_SSL", raising=False)

    assert truenas_http_verify_ssl() is True


def test_truenas_http_verify_ssl_honors_api_setting(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_API_VERIFY_SSL", "false")
    monkeypatch.setenv("TRUENAS_VERIFY_SSL", "true")

    assert truenas_http_verify_ssl() is False


def test_truenas_probe_classifies_connection_refused() -> None:
    exc = ConnectionRefusedError("Connection refused")

    assert _truenas_failure_stage(exc) == "connect_refused"


def test_truenas_probe_classifies_connection_reset() -> None:
    exc = ConnectionResetError(104, "Connection reset by peer")

    assert _truenas_failure_stage(exc) == "connection_reset"


def test_truenas_probe_logs_connect_phase_without_credentials(caplog) -> None:
    class FailingClient:
        def __enter__(self):
            raise TimeoutError("connection timed out")

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def factory(**kwargs):
        return FailingClient()

    adapter = TrueNASReadOnlyAdapter(
        TrueNASSettings(
            url="https://truenas.example:7000",
            username="readonly-user",
            api_key="super-secret-api-key",
        ),
        client_factory=factory,
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(TimeoutError):
            adapter.list_apps()

    assert "phase=connect" in caplog.text
    assert "stage=connect_timeout" in caplog.text
    assert "wss://truenas.example:7000/api/current" in caplog.text
    assert "super-secret-api-key" not in caplog.text
    assert "readonly-user" not in caplog.text


def test_truenas_probe_logs_authentication_phase(caplog) -> None:
    class AuthenticationFailureClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def login_with_api_key(self, username, api_key):
            raise RuntimeError("Failed to authenticate with API key")

        def call(self, method, *params):
            pytest.fail("API call must not run after authentication failure")

    adapter = TrueNASReadOnlyAdapter(
        TrueNASSettings(
            url="https://truenas.example:7000",
            username="readonly-user",
            api_key="super-secret-api-key",
        ),
        client_factory=lambda **kwargs: AuthenticationFailureClient(),
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="authenticate"):
            adapter.list_apps()

    assert "phase=authentication" in caplog.text
    assert "stage=authentication" in caplog.text
    assert "super-secret-api-key" not in caplog.text


def test_truenas_probe_logs_call_phase(caplog) -> None:
    class CallFailureClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def login_with_api_key(self, username, api_key):
            return True

        def call(self, method, *params):
            raise ConnectionResetError(104, "Connection reset by peer")

    adapter = TrueNASReadOnlyAdapter(
        TrueNASSettings(
            url="https://truenas.example:7000",
            username="readonly-user",
            api_key="super-secret-api-key",
        ),
        client_factory=lambda **kwargs: CallFailureClient(),
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ConnectionResetError):
            adapter.list_apps()

    assert "method=app.query" in caplog.text
    assert "phase=call" in caplog.text
    assert "stage=connection_reset" in caplog.text
