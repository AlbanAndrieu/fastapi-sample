"""Read-only Cloudflare Tunnel and Access inventory for homelab exposure audits."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

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


class CloudflareAccessPolicyObservation(BaseModel):
    """Sanitized Cloudflare Access policy facts relevant to exposure posture."""

    model_config = ConfigDict(frozen=True)

    policy_id: str
    name: str | None = None
    decision: str | None = None
    includes_everyone: bool = False


class CloudflareAccessApplicationObservation(BaseModel):
    """Observed Access application and its policies for one protected domain/path."""

    model_config = ConfigDict(frozen=True)

    app_id: str
    name: str
    domain: str
    hostname: str
    path: str = "/"
    policies: tuple[CloudflareAccessPolicyObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class CloudflareTunnelSettings:
    """Credentials required to inspect Cloudflare Tunnel and Access configuration."""

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
            "Cloudflare observation requires the official 'cloudflare' Python SDK"
        ) from exc
    return module.Cloudflare


def _value(obj: object, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _rule_includes_everyone(rule: object) -> bool:
    if isinstance(rule, dict):
        return "everyone" in rule
    return getattr(rule, "everyone", None) is not None


def _application_host_and_path(domain: str) -> tuple[str, str]:
    raw = domain.strip()
    if not raw:
        return "", "/"
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path or "/"
    return hostname, path


class CloudflareTunnelObserver:
    """Inspect Cloudflare-managed tunnels and Access without mutating state."""

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
            tunnel_id = str(_value(tunnel, "id", "") or "")
            if not tunnel_id:
                continue

            tunnel_name = str(_value(tunnel, "name", "") or tunnel_id)
            config_source = _value(tunnel, "config_src")
            ingress: tuple[CloudflareTunnelIngress, ...] = ()

            # Cloudflare exposes remote ingress through the API only for
            # dashboard-managed tunnels. Local YAML remains intentionally unknown.
            if config_source == "cloudflare":
                ingress = self._read_ingress(
                    tunnel_id=tunnel_id,
                    tunnel_name=tunnel_name,
                    status=_value(tunnel, "status"),
                )

            observations.append(
                CloudflareTunnelObservation(
                    tunnel_id=tunnel_id,
                    name=tunnel_name,
                    status=_value(tunnel, "status"),
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
        config = _value(configuration, "config")
        rules = _value(config, "ingress", ()) or ()

        observed: list[CloudflareTunnelIngress] = []
        for rule in rules:
            hostname = str(_value(rule, "hostname", "") or "").strip().lower()
            service = str(_value(rule, "service", "") or "").strip()
            if not hostname:
                # Catch-all rules such as http_status:404 are not public hostnames.
                continue
            observed.append(
                CloudflareTunnelIngress(
                    tunnel_id=tunnel_id,
                    tunnel_name=tunnel_name,
                    hostname=hostname.rstrip("."),
                    service=service,
                    status=status,
                )
            )

        return tuple(observed)

    def list_access_applications(self) -> list[CloudflareAccessApplicationObservation]:
        """Return Access apps and policies using read-only Apps/Policies permissions."""
        applications_api = self._client.zero_trust.access.applications
        page = applications_api.list(account_id=self._settings.account_id)
        observations: list[CloudflareAccessApplicationObservation] = []

        for application in page:
            app_id = str(_value(application, "id", "") or "")
            domain = str(_value(application, "domain", "") or "").strip()
            hostname, path = _application_host_and_path(domain)
            if not app_id or not hostname:
                continue

            raw_policies = _value(application, "policies")
            if raw_policies is None:
                raw_policies = applications_api.policies.list(
                    app_id,
                    account_id=self._settings.account_id,
                )

            policies: list[CloudflareAccessPolicyObservation] = []
            for policy in raw_policies or ():
                policy_id = str(_value(policy, "id", "") or "")
                if not policy_id:
                    continue
                include_rules = _value(policy, "include", ()) or ()
                policies.append(
                    CloudflareAccessPolicyObservation(
                        policy_id=policy_id,
                        name=(
                            str(_value(policy, "name"))
                            if _value(policy, "name") is not None
                            else None
                        ),
                        decision=(
                            str(_value(policy, "decision")).lower()
                            if _value(policy, "decision") is not None
                            else None
                        ),
                        includes_everyone=any(
                            _rule_includes_everyone(rule) for rule in include_rules
                        ),
                    )
                )

            observations.append(
                CloudflareAccessApplicationObservation(
                    app_id=app_id,
                    name=str(_value(application, "name", "") or app_id),
                    domain=domain,
                    hostname=hostname,
                    path=path,
                    policies=tuple(policies),
                )
            )

        return observations


def observe_cloudflare_tunnels() -> list[CloudflareTunnelObservation]:
    """Observe tunnels when configured; otherwise safely return no observations."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return []
    return CloudflareTunnelObserver(settings).list_tunnels()


def observe_cloudflare_access_applications() -> list[CloudflareAccessApplicationObservation]:
    """Observe Access apps/policies when the read-only token has the required scope."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return []
    return CloudflareTunnelObserver(settings).list_access_applications()
