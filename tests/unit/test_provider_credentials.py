"""Provider credential inventory must expose configuration state, never secret values."""

from nabla.api.provider_credentials import (
    infrastructure_provider_credentials,
    inspect_environment_credentials,
)


def _clear_pfsense_env(monkeypatch) -> None:
    for name in (
        "PFSENSE_API_URL",
        "PFSENSE_API_KEY",
        "PFSENSE_POSTURE_API_URL",
        "PFSENSE_POSTURE_API_KEY",
        "PFSENSE_SECURITY_API_URL",
        "PFSENSE_SECURITY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _clear_truenas_env(monkeypatch) -> None:
    for name in (
        "TRUENAS_API_USERNAME",
        "TRUENAS_API_KEY",
        "TRUENAS_USERNAME",
        "TRUENAS_USER",
        "TRUENAS_MCP_API_KEY",
        "TRUENAS_INFRA_API_USERNAME",
        "TRUENAS_INFRA_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_missing_provider_secret_reports_variable_name(monkeypatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.delenv("PFSENSE_API_KEY", raising=False)

    result = inspect_environment_credentials(
        "pfsense",
        "PFSENSE_API_URL",
        "PFSENSE_API_KEY",
        secret_variables=frozenset({"PFSENSE_API_KEY"}),
    ).as_dict()

    assert result["configured"] is False
    assert result["configuration_stage"] == "missing_credentials"
    assert result["missing_variables"] == ["PFSENSE_API_KEY"]


def test_environment_variable_reference_is_rejected_without_echoing_secret(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-placeholder")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "PFSENSE_API_KEY")

    result = infrastructure_provider_credentials()["cloudflare"]

    assert result["configured"] is False
    assert result["configuration_stage"] == "invalid_credential_reference"
    assert result["invalid_reference_variables"] == ["CLOUDFLARE_API_TOKEN"]
    assert "PFSENSE_API_KEY" not in repr(result)


def test_inventory_tracks_split_pfsense_identities_without_secret_material(monkeypatch) -> None:
    _clear_pfsense_env(monkeypatch)
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_API_USERNAME", "fastapi_observer")
    monkeypatch.setenv("TRUENAS_API_KEY", "7-test-placeholder")
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.setenv("PFSENSE_POSTURE_API_KEY", "posture-test-placeholder")
    monkeypatch.setenv("PFSENSE_SECURITY_API_KEY", "security-test-placeholder")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-placeholder")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-test-placeholder")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "service-client-id-placeholder")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "service-client-secret-placeholder")

    result = infrastructure_provider_credentials()

    assert set(result) == {
        "truenas",
        "pfsense",
        "pfsense_security",
        "cloudflare",
        "cloudflare_access_service_token",
    }
    assert all(provider["configured"] is True for provider in result.values())
    assert result["pfsense"]["credential_mode"] == "dedicated"
    assert result["pfsense_security"]["credential_mode"] == "dedicated"
    assert result["truenas"]["username_configured"] is True
    assert result["truenas"]["credential_mode"] == "dedicated_observer"
    serialized = repr(result)
    for secret in (
        "7-test-placeholder",
        "posture-test-placeholder",
        "security-test-placeholder",
        "cloudflare-test-placeholder",
        "service-client-id-placeholder",
        "service-client-secret-placeholder",
    ):
        assert secret not in serialized


def test_inventory_ignores_truenas_infrastructure_credentials(monkeypatch) -> None:
    _clear_truenas_env(monkeypatch)
    monkeypatch.setenv("TRUENAS_INFRA_API_USERNAME", "albandrieu")
    monkeypatch.setenv("TRUENAS_INFRA_API_KEY", "infra-test-placeholder")

    result = infrastructure_provider_credentials()["truenas"]

    assert result["configured"] is False
    assert result["username_configured"] is False
    assert result["credential_mode"] == "dedicated_observer"
    assert result["missing_variables"] == [
        "TRUENAS_API_USERNAME",
        "TRUENAS_API_KEY",
    ]
    assert "infra-test-placeholder" not in repr(result)


def test_inventory_requests_dedicated_keys_when_generic_fallback_is_absent(monkeypatch) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")

    result = infrastructure_provider_credentials()

    assert result["pfsense"]["configured"] is False
    assert result["pfsense"]["credential_mode"] == "dedicated"
    assert result["pfsense"]["missing_variables"] == ["PFSENSE_POSTURE_API_KEY"]
    assert result["pfsense_security"]["configured"] is False
    assert result["pfsense_security"]["credential_mode"] == "dedicated"
    assert result["pfsense_security"]["missing_variables"] == ["PFSENSE_SECURITY_API_KEY"]


def test_inventory_keeps_legacy_pfsense_fallback_when_explicitly_present(monkeypatch) -> None:
    _clear_pfsense_env(monkeypatch)
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "legacy-test-placeholder")

    result = infrastructure_provider_credentials()

    assert result["pfsense"]["configured"] is True
    assert result["pfsense"]["credential_mode"] == "legacy_shared"
    assert result["pfsense_security"]["configured"] is True
    assert result["pfsense_security"]["credential_mode"] == "legacy_shared"
    assert "legacy-test-placeholder" not in repr(result)


def test_cloudflare_access_service_token_requires_both_values(monkeypatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "service-client-id-placeholder")
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)

    result = infrastructure_provider_credentials()["cloudflare_access_service_token"]

    assert result["configured"] is False
    assert result["configuration_stage"] == "missing_credentials"
    assert result["missing_variables"] == ["CF_ACCESS_CLIENT_SECRET"]
    assert "service-client-id-placeholder" not in repr(result)
