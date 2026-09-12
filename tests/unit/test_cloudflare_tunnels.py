"""Tests for the read-only Cloudflare Tunnel and Access observer."""

import secrets
from types import SimpleNamespace

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelObserver,
    CloudflareTunnelSettings,
    cloudflare_api_configuration_status,
    observe_cloudflare_access_applications,
    observe_cloudflare_access_control_plane,
    observe_cloudflare_tunnels,
)


TEST_API_TOKEN = secrets.token_urlsafe(16)


class _Configurations:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def get(self, tunnel_id: str, *, account_id: str) -> object:
        self.calls.append((tunnel_id, account_id))
        return self._responses[tunnel_id]


class _Cloudflared:
    def __init__(self, tunnels: list[object], configurations: _Configurations) -> None:
        self._tunnels = tunnels
        self.configurations = configurations
        self.list_calls: list[tuple[str, bool]] = []

    def list(self, *, account_id: str, is_deleted: bool) -> list[object]:
        self.list_calls.append((account_id, is_deleted))
        return self._tunnels


class _AccessPolicies:
    def __init__(self, responses: dict[str, list[object]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def list(self, app_id: str, *, account_id: str) -> list[object]:
        self.calls.append((app_id, account_id))
        return self._responses.get(app_id, [])


class _Applications:
    def __init__(
        self,
        applications: list[object],
        policies: dict[str, list[object]],
    ) -> None:
        self._applications = applications
        self.policies = _AccessPolicies(policies)
        self.list_calls: list[str] = []

    def list(self, *, account_id: str) -> list[object]:
        self.list_calls.append(account_id)
        return self._applications


class _ReusablePolicies:
    def __init__(self, policies: list[object]) -> None:
        self._policies = policies
        self.list_calls: list[str] = []

    def list(self, *, account_id: str) -> list[object]:
        self.list_calls.append(account_id)
        return self._policies


class _ServiceTokens:
    def __init__(self, tokens: list[object]) -> None:
        self._tokens = tokens
        self.list_calls: list[str] = []

    def list(self, *, account_id: str) -> list[object]:
        self.list_calls.append(account_id)
        return self._tokens


def _client(
    *,
    tunnels: list[object],
    configurations: dict[str, object],
    access_applications: list[object] | None = None,
    access_policies: dict[str, list[object]] | None = None,
    reusable_policies: list[object] | None = None,
    service_tokens: list[object] | None = None,
) -> object:
    cloudflared = _Cloudflared(tunnels, _Configurations(configurations))
    applications = _Applications(
        access_applications or [],
        access_policies or {},
    )
    return SimpleNamespace(
        zero_trust=SimpleNamespace(
            tunnels=SimpleNamespace(cloudflared=cloudflared),
            access=SimpleNamespace(
                applications=applications,
                policies=_ReusablePolicies(reusable_policies or []),
                service_tokens=_ServiceTokens(service_tokens or []),
            ),
        ),
    )


def test_observer_bounds_sdk_requests() -> None:
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return _client(tunnels=[], configurations={})

    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="test-account", api_token=TEST_API_TOKEN),
        client_factory=factory,
    )
    assert observer.list_tunnels() == []
    assert calls == [{"api_token": TEST_API_TOKEN, "timeout": 5.0, "max_retries": 0}]


def test_settings_are_disabled_when_credentials_are_incomplete(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    assert CloudflareTunnelSettings.from_environment() is None
    assert observe_cloudflare_tunnels() == []
    assert observe_cloudflare_access_applications() == []
    assert observe_cloudflare_access_control_plane().service_token_count is None


def test_settings_reject_environment_variable_reference(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-placeholder")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "PFSENSE_API_KEY")

    status = cloudflare_api_configuration_status()

    assert status["configured"] is False
    assert status["configuration_stage"] == "invalid_credential_reference"
    assert status["invalid_reference_variables"] == ["CLOUDFLARE_API_TOKEN"]
    assert CloudflareTunnelSettings.from_environment() is None
    assert "PFSENSE_API_KEY" not in repr(status)


def test_observer_reads_remote_tunnel_public_hostnames() -> None:
    client = _client(
        tunnels=[
            SimpleNamespace(
                id="tunnel-1",
                name="homelab",
                status="healthy",
                config_src="cloudflare",
            ),
        ],
        configurations={
            "tunnel-1": SimpleNamespace(
                config=SimpleNamespace(
                    ingress=[
                        SimpleNamespace(
                            hostname="OpenWebUI.Example.COM",
                            service="http://192.0.2.10:3000",
                        ),
                        SimpleNamespace(hostname="", service="http_status:404"),
                    ],
                ),
            ),
        },
    )

    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    observations = observer.list_tunnels()

    assert len(observations) == 1
    assert observations[0].name == "homelab"
    assert observations[0].status == "healthy"
    assert len(observations[0].ingress) == 1
    assert observations[0].ingress[0].hostname == "openwebui.example.com"
    assert observations[0].ingress[0].service == "http://192.0.2.10:3000"


def test_local_tunnel_is_reported_without_guessing_its_ingress() -> None:
    client = _client(
        tunnels=[
            SimpleNamespace(
                id="tunnel-local",
                name="locally-managed",
                status="healthy",
                config_src="local",
            ),
        ],
        configurations={},
    )

    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    observations = observer.list_tunnels()

    assert len(observations) == 1
    assert observations[0].config_source == "local"
    assert observations[0].ingress == ()
    configurations = client.zero_trust.tunnels.cloudflared.configurations
    assert configurations.calls == []


def test_observer_excludes_deleted_tunnels() -> None:
    client = _client(tunnels=[], configurations={})
    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    assert observer.list_tunnels() == []
    assert client.zero_trust.tunnels.cloudflared.list_calls == [("account", False)]


def test_observer_reads_access_bypass_everyone_policy() -> None:
    client = _client(
        tunnels=[],
        configurations={},
        access_applications=[
            SimpleNamespace(
                id="app-n8n",
                name="n8n",
                domain="n8n.albandrieu.com",
                policies=None,
            ),
        ],
        access_policies={
            "app-n8n": [
                SimpleNamespace(
                    id="policy-public",
                    name="Public webhook workaround",
                    decision="bypass",
                    include=[SimpleNamespace(everyone=SimpleNamespace())],
                ),
            ],
        },
    )
    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    observations = observer.list_access_applications()

    assert len(observations) == 1
    assert observations[0].hostname == "n8n.albandrieu.com"
    assert observations[0].path == "/"
    assert observations[0].policies[0].decision == "bypass"
    assert observations[0].policies[0].includes_everyone is True
    assert client.zero_trust.access.applications.policies.calls == [("app-n8n", "account")]


def test_observer_preserves_path_scoped_access_application() -> None:
    client = _client(
        tunnels=[],
        configurations={},
        access_applications=[
            SimpleNamespace(
                id="app-webhook",
                name="n8n webhook",
                domain="n8n.albandrieu.com/webhook/*",
                policies=[
                    SimpleNamespace(
                        id="policy-webhook",
                        name="Webhook bypass",
                        decision="bypass",
                        include=[{"everyone": {}}],
                    ),
                ],
            ),
        ],
    )
    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    observations = observer.list_access_applications()

    assert observations[0].hostname == "n8n.albandrieu.com"
    assert observations[0].path == "/webhook/*"
    assert observations[0].policies[0].includes_everyone is True
    assert client.zero_trust.access.applications.policies.calls == []


def test_access_control_plane_is_sanitized_and_correlates_service_token(monkeypatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "client-current")
    client = _client(
        tunnels=[],
        configurations={},
        reusable_policies=[
            SimpleNamespace(id="policy-1", app_count=4),
            SimpleNamespace(id="policy-2", app_count=3),
        ],
        service_tokens=[
            SimpleNamespace(id="token-1", client_id="client-current", enabled=True),
            SimpleNamespace(id="token-2", client_id="client-old", enabled=False),
        ],
    )
    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token=TEST_API_TOKEN),
        client=client,
    )

    result = observer.access_control_plane()

    assert result.reusable_policy_count == 2
    assert result.reusable_policy_app_count == 7
    assert result.service_token_count == 2
    assert result.service_token_enabled_count == 1
    assert result.configured_service_token_present is True
    assert result.reusable_policy_elapsed_ms is not None
    assert result.service_token_elapsed_ms is not None
    assert "client-current" not in repr(result)
