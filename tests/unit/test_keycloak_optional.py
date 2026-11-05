"""Keycloak is optional: no client at import, skipped probe and 503 auth when unset."""

from fastapi import HTTPException
from keycloak.exceptions import KeycloakGetError
import pytest

from nabla import config_settings
from nabla.api import integration_health
from nabla.api.health_contracts import apply_diagnostic_status
from nabla.auth import service

# Trimmed copy of the page Cloudflare served for keycloak on 2026-10-30.
_DEFAULT_DENY_BODY = (
    b"<!doctype html>\n<html><head><title>This resource is blocked by this account&#39;s "
    b"&#60;strong&#62;Default-Deny&#60;/strong&#62; policy. To grant access, please contact your admin</title>"
)


def _raise(exc: Exception) -> None:
    raise exc


def test_cloudflare_default_deny_keeps_keycloak_unknown_not_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(integration_health, "keycloak_configured", lambda: True)
    error = KeycloakGetError(error_message=_DEFAULT_DENY_BODY, response_code=403, response_body=_DEFAULT_DENY_BODY)
    monkeypatch.setattr(integration_health, "get_openid_config", lambda: _raise(error))

    result = integration_health.probe_keycloak_well_known()

    assert result["reachable"] is None
    assert result["status_confirmed"] is False
    assert result["effective_state"] == "warn"
    assert result["http_status"] == 403
    assert result["public_probe_auth_mode"] == "cloudflare_access_blocked"
    assert apply_diagnostic_status({"checks": {"keycloak": result}})["status"] == "healthy"


def test_cloudflare_challenge_keeps_keycloak_unknown_not_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI Cloud egress received the 'Just a moment...' interstitial on 2026-11-04."""
    monkeypatch.setattr(integration_health, "keycloak_configured", lambda: True)
    body = b'<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>'
    error = KeycloakGetError(error_message=body, response_code=403, response_body=body)
    monkeypatch.setattr(integration_health, "get_openid_config", lambda: _raise(error))

    result = integration_health.probe_keycloak_well_known()

    assert result["reachable"] is None
    assert result["status_confirmed"] is False
    assert result["edge_block"] == "challenge"
    assert result["public_probe_auth_mode"] == "cloudflare_challenge"
    assert "origin health is unverified" in result["warning"]


def test_keycloak_origin_error_is_still_reported_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(integration_health, "keycloak_configured", lambda: True)
    error = KeycloakGetError(error_message=b"upstream failed", response_code=500, response_body=b"upstream failed")
    monkeypatch.setattr(integration_health, "get_openid_config", lambda: _raise(error))

    result = integration_health.probe_keycloak_well_known()

    assert result["reachable"] is False
    assert apply_diagnostic_status({"checks": {"keycloak": result}})["status"] == "degraded"


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
