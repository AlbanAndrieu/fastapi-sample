"""Keycloak is optional: no client at import, skipped probe and 503 auth when unset."""

from fastapi import HTTPException
import pytest

from nabla import config_settings
from nabla.api import integration_health
from nabla.auth import service


def test_unconfigured_keycloak_probe_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(integration_health, "keycloak_configured", lambda: False)

    assert integration_health.probe_keycloak_well_known() == {
        "reachable": None,
        "skipped": True,
        "reason": "KEYCLOAK_SERVER_URL is not configured",
    }


def test_unconfigured_keycloak_auth_answers_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "keycloak_configured", lambda: False)

    with pytest.raises(HTTPException) as raised:
        service.AuthService.authenticate_user("user", "password")

    assert raised.value.status_code == 503
    assert raised.value.detail == "Keycloak authentication is not configured"


def test_keycloak_client_refuses_to_build_without_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_settings, "keycloak_configured", lambda: False)
    config_settings.get_keycloak_openid.cache_clear()

    with pytest.raises(RuntimeError, match="Keycloak is not configured"):
        config_settings.get_keycloak_openid()

    config_settings.get_keycloak_openid.cache_clear()


def test_keycloak_settings_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = config_settings.APIDeploymentSettings.model_fields

    for name in ("keycloak_server_url", "keycloak_realm", "keycloak_client_id", "keycloak_client_secret"):
        assert fields[name].is_required() is False
        assert fields[name].default is None
