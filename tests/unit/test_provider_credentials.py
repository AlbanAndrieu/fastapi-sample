"""Provider credential inventory must expose configuration state, never secret values."""

from nabla.api.provider_credentials import (
    infrastructure_provider_credentials,
    inspect_environment_credentials,
)


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


def test_inventory_tracks_each_provider_without_secret_material(monkeypatch) -> None:
    monkeypatch.setenv("TRUENAS_USER", "test-user")
    monkeypatch.setenv("TRUENAS_API_KEY", "7-test-placeholder")
    monkeypatch.setenv("PFSENSE_API_URL", "https://pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "pfsense-test-placeholder")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-placeholder")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-test-placeholder")

    result = infrastructure_provider_credentials()

    assert set(result) == {"truenas", "pfsense", "cloudflare"}
    assert all(provider["configured"] is True for provider in result.values())
    assert result["truenas"]["username_configured"] is True
    serialized = repr(result)
    for secret in (
        "7-test-placeholder",
        "pfsense-test-placeholder",
        "cloudflare-test-placeholder",
    ):
        assert secret not in serialized
