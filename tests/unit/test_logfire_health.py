"""Tests for the optional Logfire health probe."""

from unittest.mock import MagicMock

from nabla.api import observability_health


def test_logfire_check_is_skipped_when_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("LOGFIRE_ENABLED", raising=False)
    monkeypatch.delenv("LOGFIRE_ENABLE", raising=False)
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)

    result = observability_health.check_logfire_connectivity()

    assert result["skipped"] is True
    assert result["reachable"] is None


def test_logfire_check_is_skipped_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LOGFIRE_ENABLED", "false")
    monkeypatch.setenv("LOGFIRE_TOKEN", "unused")

    result = observability_health.check_logfire_connectivity()

    assert result["skipped"] is True
    assert result["reachable"] is None


def test_logfire_check_fails_when_enabled_without_token(monkeypatch) -> None:
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)

    result = observability_health.check_logfire_connectivity()

    assert result["reachable"] is False
    assert "LOGFIRE_TOKEN" in result["error"]


def test_logfire_check_verifies_tls_ingestion_connectivity(monkeypatch) -> None:
    monkeypatch.setenv("LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-write-token")
    monkeypatch.setenv("LOGFIRE_BASE_URL", "https://logfire.example")

    raw_socket = MagicMock()
    raw_socket.__enter__.return_value = raw_socket
    tls_socket = MagicMock()
    tls_socket.__enter__.return_value = tls_socket
    context = MagicMock()
    context.wrap_socket.return_value = tls_socket

    create_connection = MagicMock(return_value=raw_socket)
    monkeypatch.setattr(
        observability_health.socket,
        "create_connection",
        create_connection,
    )
    monkeypatch.setattr(
        observability_health.ssl,
        "create_default_context",
        MagicMock(return_value=context),
    )

    result = observability_health.check_logfire_connectivity()

    create_connection.assert_called_once_with(("logfire.example", 443), timeout=3.0)
    context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="logfire.example")
    assert result["reachable"] is True
    assert result["tls_trusted"] is True
    assert result["probe"] == "ingest_tls_socket"
