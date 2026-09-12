"""Contracts for filtering retired Cloudflare Tunnel inventory."""

from types import SimpleNamespace

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelObserver,
    CloudflareTunnelSettings,
)


class _Page(list[object]):
    def __init__(self, items: list[object]) -> None:
        super().__init__(items)
        self.result_info = SimpleNamespace(count=len(items), total_count=len(items))


def _settings() -> CloudflareTunnelSettings:
    return CloudflareTunnelSettings(
        account_id="account",
        api_token=str("test-observer-credential"),
    )


def test_inactive_tunnels_are_excluded_without_hiding_provider_total() -> None:
    page = _Page(
        [
            SimpleNamespace(
                id="active",
                name="nabla-truescale",
                status="healthy",
                config_src="cloudflare",
            ),
            SimpleNamespace(
                id="inactive",
                name="Tunnel OVH - main",
                status="inactive",
                config_src="cloudflare",
            ),
        ],
    )
    configuration_calls: list[str] = []

    def configuration_get(tunnel_id: str, **_: object) -> object:
        configuration_calls.append(tunnel_id)
        return SimpleNamespace(config=SimpleNamespace(ingress=[]))

    client = SimpleNamespace(
        zero_trust=SimpleNamespace(
            tunnels=SimpleNamespace(
                cloudflared=SimpleNamespace(
                    list=lambda **_: page,
                    configurations=SimpleNamespace(get=configuration_get),
                ),
            ),
        ),
    )
    observer = CloudflareTunnelObserver(
        _settings(),
        client=client,
    )

    tunnels, metadata = observer.list_tunnels_with_metadata()

    assert [tunnel.name for tunnel in tunnels] == ["nabla-truescale"]
    assert configuration_calls == ["active"]
    assert metadata["result_count"] == 1
    assert metadata["total_count"] == 2
    assert metadata["inactive_filtered"] == 1


def test_degraded_tunnel_remains_visible_as_incident_evidence() -> None:
    page = _Page(
        [
            SimpleNamespace(
                id="degraded",
                name="homelab-degraded",
                status="degraded",
                config_src="local",
            ),
        ],
    )
    client = SimpleNamespace(
        zero_trust=SimpleNamespace(
            tunnels=SimpleNamespace(
                cloudflared=SimpleNamespace(
                    list=lambda **_: page,
                ),
            ),
        ),
    )
    observer = CloudflareTunnelObserver(
        _settings(),
        client=client,
    )

    tunnels, metadata = observer.list_tunnels_with_metadata()

    assert [tunnel.status for tunnel in tunnels] == ["degraded"]
    assert metadata["inactive_filtered"] == 0
