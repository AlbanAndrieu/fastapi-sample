"""Cached Cloudflare Tunnel/Access exposure observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_access_applications,
    observe_cloudflare_tunnels,
)
from nabla.api.external_probe_cache import get_or_refresh_probe
from nabla.api.provider_probe_policies import CLOUDFLARE_EXPOSURE_CACHE_POLICY

_CACHE_KEY = "cloudflare:exposure"
_OBSERVER_TIMEOUT_SEC = 4.0


def _safe_service_target(value: str) -> str:
    """Return an operator-useful Tunnel origin without credentials/query material."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        return raw[:256]
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "configured origin"
    hostname = parsed.hostname or ""
    if not hostname:
        return "configured origin"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))[:256]


def _tunnel_summary(tunnel: CloudflareTunnelObservation) -> dict[str, Any]:
    management = str(tunnel.config_source or "unknown")
    ingress = [
        {
            "hostname": item.hostname,
            "service": _safe_service_target(item.service),
            "status": item.status,
        }
        for item in tunnel.ingress
    ]
    return {
        "name": tunnel.name,
        "status": tunnel.status,
        "management": management,
        "ingress_count": len(ingress),
        "ingress_visibility": ("remote_api" if management == "cloudflare" else "local_yaml_unavailable_via_api" if management == "local" else "unknown"),
        "ingress": ingress,
    }


def _access_application_summary(
    application: CloudflareAccessApplicationObservation,
) -> dict[str, Any]:
    policies = [
        {
            "name": policy.name or "unnamed policy",
            "decision": policy.decision or "unknown",
            "includes_everyone": policy.includes_everyone,
        }
        for policy in application.policies
    ]
    return {
        "name": application.name,
        "domain": application.domain,
        "path": application.path,
        "policy_count": len(policies),
        "policies": policies,
    }


@dataclass(frozen=True, slots=True)
class CloudflareExposureSnapshot:
    """Provider observations plus explicit partial-failure/cache state."""

    configured: bool
    tunnels: tuple[CloudflareTunnelObservation, ...] = ()
    access_applications: tuple[CloudflareAccessApplicationObservation, ...] = ()
    tunnel_error: str | None = None
    access_error: str | None = None
    stale: bool = False
    refresh_error: str | None = None
    cache: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        confirmed = bool(
            self.configured and self.tunnels and not self.tunnel_error and not self.access_error and not self.stale,
        )
        warning = None
        if self.configured and not confirmed:
            reason = self.refresh_error or self.tunnel_error or self.access_error or "Cloudflare inventory is empty"
            warning = f"⚠️ Cloudflare global status could not be confirmed: {reason}"
        config_sources = [str(tunnel.config_source or "unknown") for tunnel in self.tunnels]
        local_managed = sum(source == "local" for source in config_sources)
        remote_managed = sum(source == "cloudflare" for source in config_sources)
        return {
            "status_confirmed": confirmed,
            "state": "ok" if confirmed else "unknown",
            "degraded": False,
            "effective_state": "ok" if confirmed else "warn",
            "warning": warning,
            "configured": self.configured,
            "tunnels_observed": len(self.tunnels),
            "local_managed_tunnels": local_managed,
            "cloudflare_managed_tunnels": remote_managed,
            "unknown_management_tunnels": len(config_sources) - local_managed - remote_managed,
            "tunnel_config_sources": sorted(set(config_sources)),
            "tunnels": [_tunnel_summary(tunnel) for tunnel in self.tunnels],
            "access_applications_observed": len(self.access_applications),
            "access_applications": [_access_application_summary(application) for application in self.access_applications],
            "tunnel_observer_state": ("unconfigured" if not self.configured else "error" if self.tunnel_error else "empty" if not self.tunnels else "ok"),
            "access_observer_state": ("unconfigured" if not self.configured else "error" if self.access_error else "ok"),
            "tunnel_error": self.tunnel_error,
            "access_error": self.access_error,
            "stale": self.stale,
            "refresh_error": self.refresh_error,
            "cache": self.cache,
        }

    def cache_payload(self) -> dict[str, Any]:
        tunnel_error = self.tunnel_error
        if self.configured and not self.tunnels and tunnel_error is None:
            tunnel_error = "empty_inventory"
        return {
            "configured": self.configured,
            "tunnels": [item.model_dump(mode="json") for item in self.tunnels],
            "access_applications": [item.model_dump(mode="json") for item in self.access_applications],
            "tunnel_error": tunnel_error,
            "access_error": self.access_error,
        }

    @classmethod
    def from_cache_payload(
        cls,
        payload: dict[str, Any],
        *,
        stale: bool = False,
        refresh_error: str | None = None,
        cache: dict[str, Any] | None = None,
    ) -> CloudflareExposureSnapshot:
        return cls(
            configured=bool(payload.get("configured")),
            tunnels=tuple(CloudflareTunnelObservation.model_validate(item) for item in payload.get("tunnels", []) if isinstance(item, dict)),
            access_applications=tuple(CloudflareAccessApplicationObservation.model_validate(item) for item in payload.get("access_applications", []) if isinstance(item, dict)),
            tunnel_error=str(payload["tunnel_error"]) if payload.get("tunnel_error") else None,
            access_error=str(payload["access_error"]) if payload.get("access_error") else None,
            stale=stale,
            refresh_error=refresh_error,
            cache=cache,
        )


def _short_error(exc: BaseException) -> str:
    return exc.__class__.__name__[:80]


async def _origin() -> dict[str, Any]:
    async def tunnels() -> tuple[tuple[CloudflareTunnelObservation, ...], str | None]:
        try:
            observed = await asyncio.wait_for(
                asyncio.to_thread(observe_cloudflare_tunnels),
                timeout=_OBSERVER_TIMEOUT_SEC,
            )
            result = tuple(observed)
            return result, None if result else "empty_inventory"
        except Exception as exc:  # pragma: no cover - provider/network dependent
            return (), _short_error(exc)

    async def access() -> tuple[tuple[CloudflareAccessApplicationObservation, ...], str | None]:
        try:
            observed = await asyncio.wait_for(
                asyncio.to_thread(observe_cloudflare_access_applications),
                timeout=_OBSERVER_TIMEOUT_SEC,
            )
            return tuple(observed), None
        except Exception as exc:  # pragma: no cover - provider/network/permissions dependent
            return (), _short_error(exc)

    (tunnel_items, tunnel_error), (access_items, access_error) = await asyncio.gather(
        tunnels(),
        access(),
    )
    return CloudflareExposureSnapshot(
        configured=True,
        tunnels=tunnel_items,
        access_applications=access_items,
        tunnel_error=tunnel_error,
        access_error=access_error,
    ).cache_payload()


def _success(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("tunnels") and not payload.get("tunnel_error") and not payload.get("access_error"),
    )


def _refresh_error(payload: dict[str, Any]) -> str | None:
    errors = [str(value) for value in (payload.get("tunnel_error"), payload.get("access_error")) if value]
    return ", ".join(errors) or None


async def observe_cloudflare_exposure() -> CloudflareExposureSnapshot:
    """Observe Tunnel/Access with stale-if-error and explicit empty-inventory warning."""
    if CloudflareTunnelSettings.from_environment() is None:
        return CloudflareExposureSnapshot(configured=False)
    cached = await get_or_refresh_probe(
        _CACHE_KEY,
        _origin,
        is_success=_success,
        policy=CLOUDFLARE_EXPOSURE_CACHE_POLICY,
    )
    current_error = _refresh_error(cached.value)
    if (current_error or cached.metadata.get("stale") is True) and cached.last_good:
        return CloudflareExposureSnapshot.from_cache_payload(
            cached.last_good,
            stale=True,
            refresh_error=current_error or "Cloudflare refresh in progress",
            cache=cached.metadata,
        )
    return CloudflareExposureSnapshot.from_cache_payload(
        cached.value,
        stale=bool(current_error or cached.metadata.get("stale") is True),
        refresh_error=current_error,
        cache=cached.metadata,
    )
