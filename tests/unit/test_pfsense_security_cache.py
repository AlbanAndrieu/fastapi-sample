"""Cache/freshness tests for pfSense snort2c telemetry."""

import pytest

from nabla.api import pfsense_security_observer as observer
from nabla.api.pfsense_security_observer import PfSenseSecuritySettings


def _settings() -> PfSenseSecuritySettings:
    return PfSenseSecuritySettings(
        base_url="https://pfsense.example.test:10443",
        api_key="test-only-security-key",
        verify_ssl=True,
        control_path_mode="shared_wan",
    )


@pytest.mark.asyncio
async def test_snort2c_success_is_reused_from_process_cache(monkeypatch) -> None:
    await observer.reset_snort2c_cache()
    calls = 0

    async def fetch(_settings):
        nonlocal calls
        calls += 1
        return {"name": "snort2c", "entries": []}, {
            "path": observer._SNORT2C_PATH,
            "cached": False,
            "stale": False,
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
    assert second_meta["stale"] is False
    await observer.reset_snort2c_cache()


@pytest.mark.asyncio
async def test_failed_refresh_returns_stale_table_without_clear_attribution(monkeypatch) -> None:
    await observer.reset_snort2c_cache()
    responses = [
        (
            {"name": "snort2c", "entries": []},
            {
                "path": observer._SNORT2C_PATH,
                "cached": False,
                "stale": False,
                "attempts": 1,
                "elapsed_ms": 10,
                "http_status": 200,
            },
        ),
        (
            None,
            {
                "path": observer._SNORT2C_PATH,
                "cached": False,
                "stale": False,
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
    observer._snort2c_cache_at = -999.0
    second = await observer.observe_pfsense_ingress_block(settings=_settings())

    assert first["state"] == "clear"
    assert second["state"] == "telemetry_stale"
    assert second["telemetry_available"] is True
    assert second["attribution_available"] is False
    assert second["stale"] is True
    assert second["cached"] is True
    assert second["error_kind"] == "read_timeout"
    assert second["attempts"] == 2
    assert "withheld" in second["evidence"]
    await observer.reset_snort2c_cache()
