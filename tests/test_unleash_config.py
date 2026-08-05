import os
from unittest.mock import Mock

os.environ.setdefault("KEYCLOAK_SERVER_URL", "https://keycloak.example.com")
os.environ.setdefault("KEYCLOAK_REALM", "test-realm")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test-client")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("METRICS_ENABLED", "false")

import nabla.config_settings as config_settings


def test_unleash_client_is_not_initialized_when_disabled(monkeypatch):
    client = Mock()
    monkeypatch.setattr(config_settings, "UNLEASH_ENABLED", False)
    monkeypatch.setattr(config_settings, "client", client)

    assert not config_settings.is_unleash_feature_enabled("cors")
    assert config_settings.is_unleash_feature_enabled("mcp", default_when_disabled=True)
    client.is_enabled.assert_not_called()


def test_each_feature_flag_is_evaluated_when_unleash_is_enabled(monkeypatch):
    client = Mock()
    client.is_enabled.side_effect = lambda name: name == "cors"
    monkeypatch.setattr(config_settings, "UNLEASH_ENABLED", True)
    monkeypatch.setattr(config_settings, "client", client)

    assert config_settings.is_unleash_feature_enabled("cors")
    assert not config_settings.is_unleash_feature_enabled("logging_metrics")
    assert client.is_enabled.call_count == 2
