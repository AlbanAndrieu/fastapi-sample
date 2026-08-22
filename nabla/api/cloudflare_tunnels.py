"""Read-only Cloudflare Tunnel inventory for homelab exposure audits."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class CloudflareTunnelIngress(BaseModel):
    """Observed public hostname routed through a Cloudflare Tunnel."""

    model_config = ConfigDict(frozen=True)

    tunnel_id: str
    tunnel_name: str
    hostname: str
    service: str
    status: str | None = None


class CloudflareTunnelObservation(BaseModel):
    """Read-only snapshot of one Cloudflare Tunnel and its ingress rules."""

    model_config = ConfigDict(frozen=True)

    tunnel_id: str
    name: str
    status: str | None = None
    config_source: str | None = None
    ingress: tuple[CloudflareTunnelIngress, ...] = ()


@dataclass(frozen=True, slots=True)
class CloudflareTunnelSettings:
    """Credentials required to inspect Cloudflare Tunnel configuration."""

    account_id: str
    api_token: str

    @classmethod
    def from_environment(cls) -> CloudflareTunnelSettings | None:
        """Return settings only when both read-only credentials are configured."""
        account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        if not account_id or not api_token:
            return None
        return cls(account_id=account_id, api_token=api_token)


class _CloudflareClientFactory(Protocol):
    def __call__(self, *, api_token: str) -> Any: ...


def _load_cloudflare_client() -> _CloudflareClientFactory:
    """Load the official SDK lazily so the observer stays disabled by default."""
    try:
        module = importlib.import_module("cloudflare")
    except ImportError as exc:
        raise RuntimeError(
            "Cloudflare Tunnel observation requires the official 'cloudflare' Python SDK"
        ) from exc
    return module.Cloudflare


class CloudflareTunnelObserver:
    """Inspect Cloudflare-managed tunnels without mutating Cloudflare state."""

    def __init__(
        self,
        settings: CloudflareTunnelSettings,
        *,
        client: Any | None = None,
        client_factory: _CloudflareClientFactory | None = None,
    ) -> None:
        self._settings = settings
        if client is not None:
            self._client = client
            return
        factory = client_factory or _load_cloudflare_client()
        self._client = factory(api_token=settings.api_token)

    def list_tunnels(self) -> list[CloudflareTunnelObservation]:
        """Return active Cloudflared tunnels and Cloudflare-managed public hostnames."""
        page = self._client.zero_trust.tunnels.cloudflared.list(
            account_id=self._settings.account_id,
            is_deleted=False,
        )
        observations: list[CloudflareTunnelObservation] = []

        for tunnel in page:
            tunnel_id = str(getattr(tunnel, "id", "") or "")
            if not tunnel_id:
                continue

            tunnel_name = str(getattr(tunnel, "name", "") or tunnel_id)
            config_source = getattr(tunnel, "config_src", None)
            ingress: tuple[CloudflareTunnelIngress, ...] = ()

            # Cloudflare can expose the remote configuration through the API only
            # for dashboard-managed tunnels. Local YAML remains intentionally unknown.
            if config_source == "cloudflare":
                ingress = self._read_ingress(
                    tunnel_id=tunnel_id,
                    tunnel_name=tunnel_name,
                    status=getattr(tunnel, "status", None),
                )

            observations.append(
                CloudflareTunnelObservation(
                    tunnel_id=tunnel_id,
                    name=tunnel_name,
                    status=getattr(tunnel, "status", None),
                    config_source=config_source,
                    ingress=ingress,
                )
            )

        return observations

    def _read_ingress(
        self,
        *,
        tunnel_id: str,
        tunnel_name: str,
        status: str | None,
    ) -> tuple[CloudflareTunnelIngress, ...]:
        configuration = self._client.zero_trust.tunnels.cloudflared.configurations.get(
            tunnel_id,
            account_id=self._settings.account_id,
        )
        config = getattr(configuration, "config", None)
        rules = getattr(config, "ingress", None) or ()

        observed: list[CloudflareTunnelIngress] = []
        for rule in rules:
            hostname = str(getattr(rule, "hostname", "") or "").strip().lower()
            service = str(getattr(rule, "service", "") or "").strip()
            if not hostname:
                # Catch-all rules such as http_status:404 are not public hostnames.
                continue
            observed.append(
                CloudflareTunnelIngress(
                    tunnel_id=tunnel_id,
                    tunnel_name=tunnel_name,
                    hostname=hostname,
                    service=service,
                    status=status,
                )
            )

        return tuple(observed)


def observe_cloudflare_tunnels() -> list[CloudflareTunnelObservation]:
    """Observe tunnels when configured; otherwise safely return no observations."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return []
    return CloudflareTunnelObserver(settings).list_tunnels()
