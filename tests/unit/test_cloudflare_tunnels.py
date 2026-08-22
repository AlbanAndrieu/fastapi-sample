"""Tests for the read-only Cloudflare Tunnel observer."""

from types import SimpleNamespace

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelObserver,
    CloudflareTunnelSettings,
    observe_cloudflare_tunnels,
)


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


def _client(*, tunnels: list[object], configurations: dict[str, object]) -> object:
    cloudflared = _Cloudflared(tunnels, _Configurations(configurations))
    return SimpleNamespace(
        zero_trust=SimpleNamespace(
            tunnels=SimpleNamespace(cloudflared=cloudflared),
        )
    )


def test_settings_are_disabled_when_credentials_are_incomplete(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    assert CloudflareTunnelSettings.from_environment() is None
    assert observe_cloudflare_tunnels() == []


def test_observer_reads_remote_tunnel_public_hostnames() -> None:
    client = _client(
        tunnels=[
            SimpleNamespace(
                id="tunnel-1",
                name="homelab",
                status="healthy",
                config_src="cloudflare",
            )
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
                    ]
                )
            )
        },
    )

    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token="test-token"),
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
            )
        ],
        configurations={},
    )

    observer = CloudflareTunnelObserver(
        CloudflareTunnelSettings(account_id="account", api_token="test-token"),
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
        CloudflareTunnelSettings(account_id="account", api_token="test-token"),
        client=client,
    )

    assert observer.list_tunnels() == []
    assert client.zero_trust.tunnels.cloudflared.list_calls == [("account", False)]
