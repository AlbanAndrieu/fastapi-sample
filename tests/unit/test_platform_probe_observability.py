"""Regression coverage for platform probe observability and Sickz TLS semantics."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from nabla.api import platform_health, sickz_checks
from nabla.utils import log_config


class _FakeAsyncClient:
    def __init__(self, *, response=None, error=None, captured=None, **kwargs):
        self._response = response
        self._error = error
        self._captured = captured
        if captured is not None:
            captured.update(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


@pytest.mark.asyncio
async def test_pfsense_read_timeout_is_classified_and_logged(monkeypatch, caplog) -> None:
    url = "https://172.17.0.1:10443/api/v2/system/version"
    request = httpx.Request("GET", url)
    error = httpx.ReadTimeout("timed out while reading", request=request)
    captured: dict[str, object] = {}

    monkeypatch.setenv("PFSENSE_API_URL", "https://172.17.0.1:10443")
    monkeypatch.setenv("PFSENSE_API_KEY", "test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "false")
    monkeypatch.setattr(
        platform_health.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(
            error=error,
            captured=captured,
            **kwargs,
        ),
    )

    with caplog.at_level(logging.INFO, logger=platform_health.__name__):
        result = await platform_health.check_pfsense_api()

    assert result["reachable"] is False
    assert result["error_kind"] == "read_timeout"
    assert result["failure_stage"] == "response"
    assert result["exception_type"] == "ReadTimeout"
    assert result["verify_ssl"] is False
    assert result["elapsed_ms"] >= 0
    assert result["path"] == "/api/v2/system/version"
    assert captured["verify"] is False
    assert "pfSense API liveness probe started" in caplog.text
    assert "pfSense API liveness probe failed" in caplog.text
    assert "test-key" not in caplog.text


@pytest.mark.asyncio
async def test_pfsense_success_reports_timing_and_tls_policy(monkeypatch, caplog) -> None:
    captured: dict[str, object] = {}
    response = httpx.Response(200, json={"data": {"status": "ok"}})

    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example")
    monkeypatch.setenv("PFSENSE_API_KEY", "test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "true")
    monkeypatch.setattr(
        platform_health.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(
            response=response,
            captured=captured,
            **kwargs,
        ),
    )

    with caplog.at_level(logging.INFO, logger=platform_health.__name__):
        result = await platform_health.check_pfsense_api()

    assert result["reachable"] is True
    assert result["http_status"] == 200
    assert result["verify_ssl"] is True
    assert result["tls_trusted"] is True
    assert result["path"] == "/api/v2/system/version"
    assert captured["verify"] is True
    assert "pfSense API liveness probe completed" in caplog.text
    assert "test-key" not in caplog.text


@pytest.mark.asyncio
async def test_sickz_reachability_ignores_ca_trust(monkeypatch) -> None:
    captured: dict[str, object] = {}
    response = httpx.Response(200, text="ok")
    monkeypatch.setattr(
        sickz_checks.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(
            response=response,
            captured=captured,
            **kwargs,
        ),
    )

    result = await sickz_checks._probe_url("https://self-signed.example")

    assert result == {"reachable": True, "http_status": 200}
    assert captured["verify"] is False


def test_gunicorn_error_formatter_preserves_message() -> None:
    config_path = Path(log_config.__file__).with_name("log_config.json")
    config = json.loads(config_path.read_text())

    formatter = config["formatters"]["json_error"]
    assert formatter["()"] == "nabla.utils.log_config.JsonRequestFormatter"

    record = logging.LogRecord(
        "gunicorn.error",
        logging.INFO,
        __file__,
        1,
        "worker heartbeat",
        (),
        None,
    )
    payload = json.loads(log_config.JsonRequestFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["message"] == "worker heartbeat"
