"""Transport-setting contracts that must survive the pfSense settings refactor."""

import pytest

from nabla.api import platform_health
from nabla.api.pfsense_dns_observer import PfSenseDNSSettings
from nabla.api.pfsense_security_observer import PfSenseSecuritySettings

_PFSENSE_ENV = (
    "PFSENSE_API_URL",
    "PFSENSE_API_KEY",
    "PFSENSE_API_VERIFY_SSL",
    "PFSENSE_POSTURE_API_URL",
    "PFSENSE_POSTURE_API_KEY",
    "PFSENSE_POSTURE_API_VERIFY_SSL",
    "PFSENSE_SECURITY_API_URL",
    "PFSENSE_SECURITY_API_KEY",
    "PFSENSE_SECURITY_API_VERIFY_SSL",
    "PFSENSE_SECURITY_PATH_MODE",
)


def _clear_pfsense_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PFSENSE_ENV:
        monkeypatch.delenv(name, raising=False)


def test_posture_transport_prefers_dedicated_identity_and_tls_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://shared.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "shared-test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "true")
    monkeypatch.setenv("PFSENSE_POSTURE_API_URL", "https://posture.example.test/")
    monkeypatch.setenv("PFSENSE_POSTURE_API_KEY", "posture-test-key")
    monkeypatch.setenv("PFSENSE_POSTURE_API_VERIFY_SSL", "false")

    settings = PfSenseDNSSettings.from_environment()
    transport = platform_health._pfsense_posture_transport()

    assert settings is not None
    assert settings.base_url == "https://posture.example.test"
    assert settings.api_key == "posture-test-key"
    assert settings.verify_ssl is False
    assert transport == (
        "https://posture.example.test",
        "posture-test-key",
        False,
        "dedicated_posture",
    )


def test_security_transport_prefers_dedicated_identity_and_tls_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://shared.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "shared-test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "true")
    monkeypatch.setenv("PFSENSE_SECURITY_API_URL", "https://security.example.test/")
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "security-test-key")
    monkeypatch.setenv("PFSENSE_SECURITY_API_VERIFY_SSL", "false")
    monkeypatch.setenv("PFSENSE_SECURITY_PATH_MODE", "out_of_band")

    settings = PfSenseSecuritySettings.from_environment()

    assert settings is not None
    assert settings.base_url == "https://security.example.test"
    assert settings.api_key == "security-test-key"
    assert settings.verify_ssl is False
    assert settings.control_path_mode == "out_of_band"


def test_shared_transport_is_preserved_as_explicit_compatibility_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://shared.example.test/")
    monkeypatch.setenv("PFSENSE_API_KEY", "shared-test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "false")

    posture = PfSenseDNSSettings.from_environment()
    security = PfSenseSecuritySettings.from_environment()
    liveness = platform_health._pfsense_posture_transport()

    assert posture is not None
    assert posture.base_url == "https://shared.example.test"
    assert posture.api_key == "shared-test-key"
    assert posture.verify_ssl is False

    assert security is not None
    assert security.base_url == "https://shared.example.test"
    assert security.api_key == "shared-test-key"
    assert security.verify_ssl is False
    assert security.control_path_mode == "shared_wan"

    assert liveness == (
        "https://shared.example.test",
        "shared-test-key",
        False,
        "legacy_shared",
    )



@pytest.mark.asyncio
async def test_invalid_tls_values_fail_soft_across_pfsense_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://shared.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "shared-test-key")
    monkeypatch.setenv("PFSENSE_API_VERIFY_SSL", "sometimes")

    assert PfSenseDNSSettings.from_environment() is None
    assert PfSenseSecuritySettings.from_environment() is None

    result = await platform_health.check_pfsense_api()

    assert result["reachable"] is False
    assert result["configuration_stage"] == "invalid_configuration"
    assert result["invalid_configuration_variables"] == ["PFSENSE_API_VERIFY_SSL"]
    assert "shared-test-key" not in repr(result)


def test_invalid_dedicated_security_mode_is_reported_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_SECURITY_API_URL", "https://security.example.test")
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "security-test-key")
    monkeypatch.setenv("PFSENSE_SECURITY_PATH_MODE", "automatic")

    assert PfSenseSecuritySettings.from_environment() is None
