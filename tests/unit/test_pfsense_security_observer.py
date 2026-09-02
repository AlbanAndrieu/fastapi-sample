"""Tests for least-privilege pfSense/Snort security telemetry."""

from nabla.api import pfsense_security_observer as observer
from nabla.api.pfsense_security_observer import PfSenseSecuritySettings


def _settings(mode="shared_wan") -> PfSenseSecuritySettings:
    return PfSenseSecuritySettings(
        base_url="https://pfsense.example.test:10443",
        api_key="test-only-security-key",
        verify_ssl=True,
        control_path_mode=mode,
    )


def _clear_security_env(monkeypatch) -> None:
    for name in (
        "PFSENSE_API_URL",
        "PFSENSE_API_KEY",
        "PFSENSE_API_VERIFY_SSL",
        "PFSENSE_SECURITY_API_URL",
        "PFSENSE_SECURITY_API_KEY",
        "PFSENSE_SECURITY_API_VERIFY_SSL",
        "PFSENSE_SECURITY_PATH_MODE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_security_configuration_documents_exact_get_privilege(monkeypatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test:10443")
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "test-only-security-key")

    status = observer.security_configuration_status()

    assert status["configured"] is True
    assert status["required_privilege"] == "api-v2-diagnostics-table-get"
    assert status["write_privileges_required"] is False
    assert status["credential_mode"] == "dedicated_security"


def test_security_settings_prefer_dedicated_key_over_legacy(monkeypatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test:10443")
    monkeypatch.setenv("PFSENSE_API_KEY", "legacy-key")
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "dedicated-key")

    settings = observer.PfSenseSecuritySettings.from_environment()

    assert settings is not None
    assert settings.base_url == "https://pfsense.example.test:10443"
    assert settings.api_key == "dedicated-key"
    assert settings.verify_ssl is True


def test_security_settings_allow_fully_dedicated_transport(monkeypatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv(
        "PFSENSE_SECURITY_API_URL",
        "https://security-pfsense.example.test:10443",
    )
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "dedicated-key")
    monkeypatch.setenv("PFSENSE_SECURITY_API_VERIFY_SSL", "false")

    settings = observer.PfSenseSecuritySettings.from_environment()

    assert settings is not None
    assert settings.base_url == "https://security-pfsense.example.test:10443"
    assert settings.api_key == "dedicated-key"
    assert settings.verify_ssl is False


def test_security_settings_keep_legacy_fallback(monkeypatch) -> None:
    _clear_security_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test:10443")
    monkeypatch.setenv("PFSENSE_API_KEY", "legacy-key")

    status = observer.security_configuration_status()
    settings = observer.PfSenseSecuritySettings.from_environment()

    assert status["configured"] is True
    assert status["credential_mode"] == "legacy_shared"
    assert settings is not None
    assert settings.api_key == "legacy-key"


def test_exact_observed_egress_is_attributed_to_snort2c() -> None:
    result = observer._block_evidence(
        table={
            "name": "snort2c",
            "entries": ["34.200.20.162", "203.0.113.10"],
        },
        egress={"ip": "34.200.20.162", "observed": True},
        settings=_settings(),
    )

    assert result["state"] == "blocked"
    assert result["mechanism"] == "snort2c"
    assert result["source"]["ip"] == "34.200.20.162"
    assert result["destination"] == {
        "ip": "82.66.4.247",
        "port": 7000,
        "role": "pfSense WAN / homelab public endpoint",
    }
    assert result["control_path"]["blind_spot"] is True


def test_different_egress_is_clear() -> None:
    result = observer._block_evidence(
        table={"name": "snort2c", "entries": "52.1.10.241 54.164.107.133"},
        egress={"ip": "34.200.20.162", "observed": True},
        settings=_settings(),
    )

    assert result["state"] == "clear"


def test_out_of_band_control_path_is_marked_independent() -> None:
    result = observer._block_evidence(
        table={"name": "snort2c", "entries": []},
        egress={"ip": "52.1.10.241", "observed": True},
        settings=_settings("out_of_band"),
    )

    assert result["control_path"]["mode"] == "out_of_band"
    assert result["control_path"]["independent_from_wan_filter"] is True
    assert result["control_path"]["blind_spot"] is False


def test_unavailable_shared_wan_path_reports_blind_spot() -> None:
    result = observer._unavailable(_settings(), "snort2c telemetry unavailable: timeout")

    assert result["state"] == "telemetry_unavailable"
    assert result["control_path"]["mode"] == "shared_wan"
    assert result["control_path"]["blind_spot"] is True
