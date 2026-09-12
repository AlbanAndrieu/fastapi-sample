"""Cached Cloudflare Tunnel/Access exposure observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareAccessControlPlaneObservation,
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_access_applications_with_metadata,
    observe_cloudflare_access_control_plane,
    observe_cloudflare_tunnels_with_metadata,
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
        "ingress_visibility": (
            "remote_api"
            if management == "cloudflare"
            else "local_yaml_unavailable_via_api"
            if management == "local"
            else "unknown"
        ),
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


def _api_family(
    *,
    result_count: int | None,
    total_count: int | None,
    elapsed_ms: int | None,
    error: str | None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "state": "error" if error else "ok",
        "success": error is None,
        "result_count": result_count,
        "total_count": total_count,
        "elapsed_ms": elapsed_ms,
        "error": error,
        **extra,
    }


@dataclass(frozen=True, slots=True)
class CloudflareExposureSnapshot:
    """Provider observations plus explicit partial-failure/cache state."""

    configured: bool
    tunnels: tuple[CloudflareTunnelObservation, ...] = ()
    access_applications: tuple[CloudflareAccessApplicationObservation, ...] = ()
    tunnel_error: str | None = None
    access_error: str | None = None
    tunnel_elapsed_ms: int | None = None
    access_elapsed_ms: int | None = None
    tunnel_result_count: int | None = None
    tunnel_total_count: int | None = None
    access_result_count: int | None = None
    access_total_count: int | None = None
    access_control_plane: CloudflareAccessControlPlaneObservation | None = None
    stale: bool = False
    refresh_error: str | None = None
    cache: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        confirmed = bool(
            self.configured
            and self.tunnels
            and not self.tunnel_error
            and not self.access_error
            and not self.stale,
        )
        warning = None
        if self.configured and not confirmed:
            reason = self.refresh_error or self.tunnel_error or self.access_error or "Cloudflare inventory is empty"
            warning = f"⚠️ Cloudflare global status could not be confirmed: {reason}"
        config_sources = [str(tunnel.config_source or "unknown") for tunnel in self.tunnels]
        local_managed = sum(source == "local" for source in config_sources)
        remote_managed = sum(source == "cloudflare" for source in config_sources)
        control = self.access_control_plane or CloudflareAccessControlPlaneObservation()
        control_plane = {
            "tunnels": _api_family(
                result_count=self.tunnel_result_count if self.tunnel_result_count is not None else len(self.tunnels),
                total_count=self.tunnel_total_count if self.tunnel_total_count is not None else len(self.tunnels),
                elapsed_ms=self.tunnel_elapsed_ms,
                error=self.tunnel_error,
            ),
            "access_applications": _api_family(
                result_count=self.access_result_count if self.access_result_count is not None else len(self.access_applications),
                total_count=self.access_total_count if self.access_total_count is not None else len(self.access_applications),
                elapsed_ms=self.access_elapsed_ms,
                error=self.access_error,
            ),
            "access_reusable_policies": _api_family(
                result_count=control.reusable_policy_count,
                total_count=control.reusable_policy_total_count,
                elapsed_ms=control.reusable_policy_elapsed_ms,
                error=control.reusable_policy_error,
                application_assignments=control.reusable_policy_app_count,
            ),
            "access_service_tokens": _api_family(
                result_count=control.service_token_count,
                total_count=control.service_token_total_count,
                elapsed_ms=control.service_token_elapsed_ms,
                error=control.service_token_error,
                enabled_count=control.service_token_enabled_count,
                configured_client_id_present=control.configured_service_token_present,
            ),
        }
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
            "control_plane": control_plane,
            "tunnel_observer_state": (
                "unconfigured"
                if not self.configured
                else "error"
                if self.tunnel_error
                else "empty"
                if not self.tunnels
                else "ok"
            ),
            "access_observer_state": (
                "unconfigured" if not self.configured else "error" if self.access_error else "ok"
            ),
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
            "tunnel_elapsed_ms": self.tunnel_elapsed_ms,
            "access_elapsed_ms": self.access_elapsed_ms,
            "tunnel_result_count": self.tunnel_result_count,
            "tunnel_total_count": self.tunnel_total_count,
            "access_result_count": self.access_result_count,
            "access_total_count": self.access_total_count,
            "access_control_plane": (
                self.access_control_plane.model_dump(mode="json")
                if self.access_control_plane is not None
                else None
            ),
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
        raw_control = payload.get("access_control_plane")
        return cls(
            configured=bool(payload.get("configured")),
            tunnels=tuple(
                CloudflareTunnelObservation.model_validate(item)
                for item in payload.get("tunnels", [])
                if isinstance(item, dict)
            ),
            access_applications=tuple(
                CloudflareAccessApplicationObservation.model_validate(item)
                for item in payload.get("access_applications", [])
                if isinstance(item, dict)
            ),
            tunnel_error=str(payload["tunnel_error"]) if payload.get("tunnel_error") else None,
            access_error=str(payload["access_error"]) if payload.get("access_error") else None,
            tunnel_elapsed_ms=payload.get("tunnel_elapsed_ms"),
            access_elapsed_ms=payload.get("access_elapsed_ms"),
            tunnel_result_count=payload.get("tunnel_result_count"),
            tunnel_total_count=payload.get("tunnel_total_count"),
            access_result_count=payload.get("access_result_count"),
            access_total_count=payload.get("access_total_count"),
            access_control_plane=(
                CloudflareAccessControlPlaneObservation.model_validate(raw_control)
                if isinstance(raw_control, dict)
                else None
            ),
            stale=stale,
            refresh_error=refresh_error,
            cache=cache,
        )


def _short_error(exc: BaseException) -> str:
    return exc.__class__.__name__[:80]


async def _origin() -> dict[str, Any]:
    async def tunnels() -> tuple[
        tuple[CloudflareTunnelObservation, ...],
        str | None,
        int,
        dict[str, int],
    ]:
        started = time.perf_counter()
        try:
            observed, metadata = await asyncio.wait_for(
                asyncio.to_thread(observe_cloudflare_tunnels_with_metadata),
                timeout=_OBSERVER_TIMEOUT_SEC,
            )
            result = tuple(observed)
            return result, None if result else "empty_inventory", round((time.perf_counter() - started) * 1000), metadata
        except Exception as exc:  # pragma: no cover - provider/network dependent
            return (), _short_error(exc), round((time.perf_counter() - started) * 1000), {}

    async def access() -> tuple[
        tuple[CloudflareAccessApplicationObservation, ...],
        str | None,
        int,
        dict[str, int],
    ]:
        started = time.perf_counter()
        try:
            observed, metadata = await asyncio.wait_for(
                asyncio.to_thread(observe_cloudflare_access_applications_with_metadata),
                timeout=_OBSERVER_TIMEOUT_SEC,
            )
            return tuple(observed), None, round((time.perf_counter() - started) * 1000), metadata
        except Exception as exc:  # pragma: no cover - provider/network/permissions dependent
            return (), _short_error(exc), round((time.perf_counter() - started) * 1000), {}

    async def control_plane() -> CloudflareAccessControlPlaneObservation:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(observe_cloudflare_access_control_plane),
                timeout=_OBSERVER_TIMEOUT_SEC,
            )
        except Exception as exc:  # pragma: no cover - provider/network/permissions dependent
            error = _short_error(exc)
            return CloudflareAccessControlPlaneObservation(
                reusable_policy_error=error,
                service_token_error=error,
            )

    tunnel_result, access_result, control = await asyncio.gather(
        tunnels(),
        access(),
        control_plane(),
    )
    tunnel_items, tunnel_error, tunnel_elapsed_ms, tunnel_metadata = tunnel_result
    access_items, access_error, access_elapsed_ms, access_metadata = access_result
    return CloudflareExposureSnapshot(
        configured=True,
        tunnels=tunnel_items,
        access_applications=access_items,
        tunnel_error=tunnel_error,
        access_error=access_error,
        tunnel_elapsed_ms=tunnel_elapsed_ms,
        access_elapsed_ms=access_elapsed_ms,
        tunnel_result_count=tunnel_metadata.get("result_count"),
        tunnel_total_count=tunnel_metadata.get("total_count"),
        access_result_count=access_metadata.get("result_count"),
        access_total_count=access_metadata.get("total_count"),
        access_control_plane=control,
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
