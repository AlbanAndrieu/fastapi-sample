"""Tests for network-stage diagnostics used by TrueNAS probes."""

import logging
import socket
import ssl

import httpx
import pytest

from nabla.api.health_checks import _probe_failure_stage
from nabla.integrations.truenas_client import (
    TrueNASReadOnlyAdapter,
    TrueNASSettings,
    _truenas_failure_stage,
)


def test_http_probe_classifies_dns_failure() -> None:
    exc = socket.gaierror(-2, "Name or service not known")

    assert _probe_failure_stage(exc) == "dns"


def test_http_probe_classifies_tls_failure() -> None:
    exc = ssl.SSLError("certificate verify failed")

    assert _probe_failure_stage(exc) == "tls"


def test_http_probe_classifies_connect_timeout() -> None:
    exc = httpx.ConnectTimeout("connection timed out")

    assert _probe_failure_stage(exc) == "connect_timeout"


def test_truenas_probe_classifies_connection_refused() -> None:
    exc = ConnectionRefusedError("Connection refused")

    assert _truenas_failure_stage(exc) == "connect_refused"


def test_truenas_probe_logs_stage_without_credentials(caplog) -> None:
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

    assert "stage=connect_timeout" in caplog.text
    assert "wss://truenas.example:7000/api/current" in caplog.text
    assert "super-secret-api-key" not in caplog.text
    assert "readonly-user" not in caplog.text
