"""Cache/freshness tests for pfSense snort2c telemetry."""

import pytest

from nabla.api import external_probe_cache
from nabla.api import pfsense_security_observer as observer
from nabla.api.pfsense_security_observer import PfSenseSecuritySettings


def _settings() -> PfSenseSecuritySettings:
    return PfSenseSecuritySettings(
        base_url="https://pfsense.example.test:10443",
        api_key="test-only-security-key",
        verify_ssl=True,
        control_path_mode="shared_wan",
    )


def _expire_current_value(key: str) -> None:
    envelope, stored_at = external_probe_cache._l1[key]
    envelope["current"]["fetched_at"] = 0.0
    external_probe_cache._l1[key] = (envelope, stored_at)


@pytest.mark.asyncio
async def test_snort2c_success_is_reused_from_l1_cache(monkeypatch) -> None:
    await observer.reset_snort2c_cache()
    calls = 0

    async def fetch(_settings):
        nonlocal calls
        calls += 1
        return {"name": "snort2c", "entries": []}, {
            "path": observer._SNORT2C_PATH,
            "attempts": 1,
            "elapsed_ms": 10,
            "http_status": 200,
        }

    monkeypatch.setattr(observer, "_fetch_snort2c", fetch)

    first, first_meta = await observer._read_snort2c_cached(_settings())
    second, second_meta = await observer._read_snort2c_cached(_settings())

    assert calls == 1
    assert first == second
    assert first_meta["cached"] is False
    assert second_meta["cached"] is True
    assert second_meta["cache_layer"] == "l1"
    assert second_meta["stale"] is False
    await observer.reset_snort2c_cache()


@pytest.mark.asyncio
async def test_failed_refresh_returns_stale_table_without_clear_attribution(monkeypatch) -> None:
    await observer.reset_snort2c_cache()
    calls = 0
    responses = [
        (
            {"name": "snort2c", "entries": []},
            {
                "path": observer._SNORT2C_PATH,
                "attempts": 1,
                "elapsed_ms": 10,
                "http_status": 200,
            },
        ),
        (
            None,
            {
                "path": observer._SNORT2C_PATH,
                "attempts": 2,
                "elapsed_ms": 5200,
                "error_kind": "read_timeout",
                "failure_stage": "response",
                "exception_type": "ReadTimeout",
                "refresh_error": "timeout",
            },
        ),
    ]

    async def fetch(_settings):
        nonlocal calls
        calls += 1
        return responses.pop(0)

    async def egress():
        return {
            "ip": "34.200.20.162",
            "observed": True,
            "cached": False,
            "source": "external_echo",
        }

    monkeypatch.setattr(observer, "_fetch_snort2c", fetch)
    monkeypatch.setattr(observer, "observe_public_egress_ip", egress)

    first = await observer.observe_pfsense_ingress_block(settings=_settings())
    _expire_current_value(observer._SNORT2C_CACHE_KEY)
    second = await observer.observe_pfsense_ingress_block(settings=_settings())
    third = await observer.observe_pfsense_ingress_block(settings=_settings())

    assert first["state"] == "clear"
    assert second["state"] == "telemetry_stale"
    assert third["state"] == "telemetry_stale"
    assert calls == 2
    for result in (second, third):
        assert result["telemetry_available"] is True
        assert result["attribution_available"] is False
        assert result["stale"] is True
        assert result["cached"] is True
        assert result["error_kind"] == "read_timeout"
        assert result["attempts"] == 2
        assert "withheld" in result["evidence"]
    await observer.reset_snort2c_cache()
