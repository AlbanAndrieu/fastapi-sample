"""Cache and transport-classification tests for the TrueNAS API health observer."""

import pytest

from nabla.api import external_probe_cache
from nabla.api import truenas_health_observer as observer


def _valid_configuration(monkeypatch) -> None:
    monkeypatch.setattr(observer, "truenas_api_configuration_failure", lambda: None)
    monkeypatch.setattr(observer, "_report_failure_to_sentry", lambda _exc, _signature: None)


def _expire_current_value(key: str) -> None:
    envelope, stored_at = external_probe_cache._l1[key]
    envelope["current"]["fetched_at"] = 0.0
    external_probe_cache._l1[key] = (envelope, stored_at)


@pytest.mark.asyncio
async def test_successful_truenas_api_probe_is_reused(monkeypatch) -> None:
    await observer.reset_truenas_health_cache()
    _valid_configuration(monkeypatch)
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        return {
            "reachable": True,
            "version": "26.0.0-BETA.2",
            "apps": [],
        }

    monkeypatch.setattr(observer, "observe_truenas_api", probe)

    first = await observer.observe_truenas_health_api()
    second = await observer.observe_truenas_health_api()

    assert calls == 1
    assert first["reachable"] is True
    assert first["cached"] is False
    assert first["stale"] is False
    assert second["reachable"] is True
    assert second["cached"] is True
    assert second["cache_layer"] == "l1"
    assert second["last_success_at"] == first["last_success_at"]
    await observer.reset_truenas_health_cache()


@pytest.mark.asyncio
async def test_health_payload_exposes_only_credential_variable_selection(monkeypatch) -> None:
    await observer.reset_truenas_health_cache()
    _valid_configuration(monkeypatch)
    monkeypatch.setenv("TRUENAS_API_USERNAME", "fastapi_observer")
    monkeypatch.setenv("TRUENAS_USER", "legacy-admin")
    monkeypatch.setenv("TRUENAS_API_KEY", "8-secret-material")
    monkeypatch.setenv("TRUENAS_MCP_API_KEY", "7-legacy-secret")

    monkeypatch.setattr(
        observer,
        "observe_truenas_api",
        lambda: {"reachable": True, "version": "26.0.0-BETA.2", "apps": []},
    )

    result = await observer.observe_truenas_health_api()

    assert result["credential_selection"] == {
        "username_variable": "TRUENAS_API_USERNAME",
        "api_key_variable": "TRUENAS_API_KEY",
        "shadowed_username_variables": ["TRUENAS_USER"],
        "shadowed_api_key_variables": ["TRUENAS_MCP_API_KEY"],
    }
    rendered = repr(result)
    assert "fastapi_observer" not in rendered
    assert "legacy-admin" not in rendered
    assert "8-secret-material" not in rendered
    assert "7-legacy-secret" not in rendered
    await observer.reset_truenas_health_cache()


@pytest.mark.asyncio
async def test_connection_reset_is_negative_cached(monkeypatch) -> None:
    await observer.reset_truenas_health_cache()
    _valid_configuration(monkeypatch)
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr(observer, "observe_truenas_api", probe)

    first = await observer.observe_truenas_health_api()
    second = await observer.observe_truenas_health_api()

    assert calls == 1
    assert first["reachable"] is False
    assert first["phase"] == "connect"
    assert first["stage"] == "connection_reset"
    assert first["exception_type"] == "ConnectionResetError"
    assert first["cached"] is False
    assert second["reachable"] is False
    assert second["stage"] == "connection_reset"
    assert second["cached"] is True
    assert second["retry_after_seconds"] == 120
    await observer.reset_truenas_health_cache()


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_as_stale_evidence(monkeypatch) -> None:
    await observer.reset_truenas_health_cache()
    _valid_configuration(monkeypatch)
    responses = [
        {
            "reachable": True,
            "version": "26.0.0-BETA.2",
            "apps": [{"name": "open-webui", "state": "RUNNING"}],
        },
        ConnectionResetError(104, "Connection reset by peer"),
    ]

    def probe():
        result = responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(observer, "observe_truenas_api", probe)

    healthy = await observer.observe_truenas_health_api()
    _expire_current_value(observer._CACHE_KEY)
    failed = await observer.observe_truenas_health_api()

    assert healthy["reachable"] is True
    assert failed["reachable"] is False
    assert failed["stage"] == "connection_reset"
    assert failed["stale"] is True
    assert failed["last_good"]["version"] == "26.0.0-BETA.2"
    assert failed["last_good"]["apps"][0]["name"] == "open-webui"
    assert failed["last_success_at"] == healthy["last_success_at"]
    await observer.reset_truenas_health_cache()


def test_tls_handshake_timeout_is_distinct_from_api_timeout() -> None:
    phase, stage = observer._failure_kind(
        TimeoutError("_ssl.c:1015: The handshake operation timed out")
    )

    assert phase == "connect"
    assert stage == "tls_handshake_timeout"


def test_call_timeout_class_name_is_classified_as_api_timeout() -> None:
    CallTimeout = type("CallTimeout", (Exception,), {})

    phase, stage = observer._failure_kind(CallTimeout("Call timeout"))

    assert phase == "api"
    assert stage == "api_call_timeout"
