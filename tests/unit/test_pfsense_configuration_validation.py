"""pfSense credential status includes canonical URL validation."""

import pytest

from nabla.api.pfsense_dns_observer import (
    PfSenseDNSSettings,
    observe_pfsense_dns_posture,
    pfsense_api_configuration_status,
)


def test_invalid_api_url_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "pfsense-test-placeholder")

    status = pfsense_api_configuration_status()

    assert status["configured"] is False
    assert status["configuration_stage"] == "invalid_configuration"
    assert status["invalid_configuration_variables"] == ["PFSENSE_API_URL"]
    assert PfSenseDNSSettings.from_environment() is None


@pytest.mark.asyncio
async def test_invalid_api_url_stays_explicit_in_observer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFSENSE_API_URL", "pfsense.example.test")
    monkeypatch.setenv("PFSENSE_API_KEY", "pfsense-test-placeholder")

    result = await observe_pfsense_dns_posture()

    assert result["configured"] is False
    assert result["reachable"] is None
    assert result["configuration_stage"] == "invalid_configuration"
    assert result["invalid_configuration_variables"] == ["PFSENSE_API_URL"]
