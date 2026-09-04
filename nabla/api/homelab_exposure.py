"""Sanitized declared-versus-observed Cloudflare exposure evidence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_access_applications,
    observe_cloudflare_tunnels,
)
from nabla.api.external_probe_cache import get_or_refresh_probe
from nabla.api.homelab_models import HomelabService
from nabla.api.provider_probe_policies import (
    CLOUDFLARE_EXPOSURE_CACHE_POLICY as _CLOUDFLARE_EXPOSURE_CACHE_POLICY,
)

_CLOUDFLARE_EXPOSURE_CACHE_KEY = "cloudflare:exposure"


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
        return {
            "configured": self.configured,
            "tunnels_observed": len(self.tunnels),
            "access_applications_observed": len(self.access_applications),
            "tunnel_observer_state": (
                "unconfigured"
                if not self.configured
                else "error"
                if self.tunnel_error
                else "ok"
            ),
            "access_observer_state": (
                "unconfigured"
                if not self.configured
                else "error"
                if self.access_error
                else "ok"
            ),
            "tunnel_error": self.tunnel_error,
            "access_error": self.access_error,
            "stale": self.stale,
            "refresh_error": self.refresh_error,
            "cache": self.cache,
        }

    def cache_payload(self) -> dict[str, Any]:
        """Return JSON-only provider evidence suitable for shared Redis storage."""
        return {
            "configured": self.configured,
            "tunnels": [item.model_dump(mode="json") for item in self.tunnels],
            "access_applications": [
                item.model_dump(mode="json") for item in self.access_applications
            ],
            "tunnel_error": self.tunnel_error,
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
            tunnel_error=(
                str(payload["tunnel_error"]) if payload.get("tunnel_error") else None
            ),
            access_error=(
                str(payload["access_error"]) if payload.get("access_error") else None
            ),
            stale=stale,
            refresh_error=refresh_error,
            cache=cache,
        )


def _short_provider_error(exc: BaseException) -> str:
    """Expose only a bounded exception class, never provider response bodies."""
    return exc.__class__.__name__[:80]


async def _observe_cloudflare_exposure_origin() -> dict[str, Any]:
    async def tunnels() -> tuple[tuple[CloudflareTunnelObservation, ...], str | None]:
        try:
            return tuple(await asyncio.to_thread(observe_cloudflare_tunnels)), None
        except Exception as exc:  # pragma: no cover - provider/network dependent
            return (), _short_provider_error(exc)

    async def access() -> tuple[
        tuple[CloudflareAccessApplicationObservation, ...], str | None
    ]:
        try:
            observed = await asyncio.to_thread(observe_cloudflare_access_applications)
            return tuple(observed), None
        except Exception as exc:  # pragma: no cover - provider/network/permissions dependent
            return (), _short_provider_error(exc)

    tunnel_result, access_result = await asyncio.gather(tunnels(), access())
    tunnel_observations, tunnel_error = tunnel_result
    access_observations, access_error = access_result
    return CloudflareExposureSnapshot(
        configured=True,
        tunnels=tunnel_observations,
        access_applications=access_observations,
        tunnel_error=tunnel_error,
        access_error=access_error,
    ).cache_payload()


def _cloudflare_exposure_success(payload: dict[str, Any]) -> bool:
    return not payload.get("tunnel_error") and not payload.get("access_error")


def _refresh_error(payload: dict[str, Any]) -> str | None:
    errors = [
        str(value)
        for value in (payload.get("tunnel_error"), payload.get("access_error"))
        if value
    ]
    return ", ".join(errors) or None


async def observe_cloudflare_exposure() -> CloudflareExposureSnapshot:
    """Observe Tunnel and Access through L1/Redis cache with stale-if-error."""
    if CloudflareTunnelSettings.from_environment() is None:
        return CloudflareExposureSnapshot(configured=False)

    cached = await get_or_refresh_probe(
        _CLOUDFLARE_EXPOSURE_CACHE_KEY,
        _observe_cloudflare_exposure_origin,
        is_success=_cloudflare_exposure_success,
        policy=_CLOUDFLARE_EXPOSURE_CACHE_POLICY,
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
        cache=cached.metadata,
    )


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _tunnels_by_hostname(
    observations: Iterable[CloudflareTunnelObservation],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tunnel in observations:
        for ingress in tunnel.ingress:
            result[ingress.hostname.lower().rstrip(".")] = {
                "cloudflare_tunnel_observed": True,
                "cloudflare_tunnel_name": ingress.tunnel_name or tunnel.name,
                "cloudflare_tunnel_status": ingress.status or tunnel.status,
            }
    return result


def _access_by_hostname(
    observations: Iterable[CloudflareAccessApplicationObservation],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[CloudflareAccessApplicationObservation]] = {}
    for application in observations:
        grouped.setdefault(application.hostname.lower().rstrip("."), []).append(application)

    result: dict[str, dict[str, Any]] = {}
    for hostname, applications in grouped.items():
        decisions: set[str] = set()
        public_scopes: set[str] = set()
        policy_count = 0
        public_policy_count = 0
        for application in applications:
            root_scope = application.path in {"", "/", "/*", "*"}
            for policy in application.policies:
                policy_count += 1
                decision = (policy.decision or "").strip().lower()
                if decision:
                    decisions.add(decision)
                public = decision == "bypass" or (
                    decision == "allow" and policy.includes_everyone
                )
                if public:
                    public_policy_count += 1
                    public_scopes.add("host" if root_scope else "path")

        result[hostname] = {
            "cloudflare_access_observed": True,
            "cloudflare_access_application_count": len(applications),
            "cloudflare_access_policy_count": policy_count,
            "cloudflare_access_policy_decisions": sorted(decisions),
            "cloudflare_access_public": public_policy_count > 0,
            "cloudflare_access_public_policy_count": public_policy_count,
            "cloudflare_access_public_scope": (
                "host"
                if "host" in public_scopes
                else "path"
                if "path" in public_scopes
                else None
            ),
        }
    return result


def _declared_edge_mode(service: HomelabService) -> str:
    if service.tunnel_secure is True:
        return "cloudflare"
    if service.tunnel_secure is False:
        return "direct"
    return "unspecified"


def _service_exposure(
    service: HomelabService,
    row: dict[str, Any],
    *,
    tunnel: dict[str, Any] | None,
    access: dict[str, Any] | None,
    snapshot: CloudflareExposureSnapshot,
) -> dict[str, Any]:
    edge_mode = _declared_edge_mode(service)
    access_required = service.effective_cloudflare_access_required
    declared = {
        "external": service.external,
        "endpoint_enabled": service.endpoint_enabled,
        "edge_mode": edge_mode,
        "cloudflare_access_required": access_required,
        "security_exception_declared": bool(service.security_exception),
    }
    observed = {
        "public_https_reachable": bool(row.get("reachable"))
        if row.get("http_status", 0) or row.get("reachable")
        else None,
        "cloudflare_tunnel_observed": bool(tunnel),
        "cloudflare_tunnel_name": tunnel.get("cloudflare_tunnel_name") if tunnel else None,
        "cloudflare_tunnel_status": tunnel.get("cloudflare_tunnel_status") if tunnel else None,
        "cloudflare_access_observed": bool(access),
        "cloudflare_access_application_count": (
            access.get("cloudflare_access_application_count") if access else 0
        ),
        "cloudflare_access_policy_count": (
            access.get("cloudflare_access_policy_count") if access else 0
        ),
        "cloudflare_access_policy_decisions": (
            access.get("cloudflare_access_policy_decisions") if access else []
        ),
        "cloudflare_access_public": (
            access.get("cloudflare_access_public") if access else None
        ),
        "cloudflare_access_public_scope": (
            access.get("cloudflare_access_public_scope") if access else None
        ),
        "cloudflare_access_public_policy_count": (
            access.get("cloudflare_access_public_policy_count") if access else 0
        ),
    }

    if not service.external or service.endpoint_enabled is False:
        return {
            "state": "not_applicable",
            "reasons": [],
            "declared": declared,
            "observed": observed,
        }

    mismatches: list[str] = []
    incomplete: list[str] = []
    if edge_mode == "unspecified":
        incomplete.append("External service has no explicit edge-mode declaration")
    elif edge_mode == "cloudflare":
        if not snapshot.configured:
            incomplete.append("Cloudflare observation is not configured")
        elif snapshot.tunnel_error:
            incomplete.append("Cloudflare Tunnel observation failed")
        elif not tunnel:
            mismatches.append(
                "Cloudflare edge is declared but no matching Tunnel ingress was observed"
            )
    elif edge_mode == "direct" and tunnel:
        mismatches.append(
            "Direct exposure is declared but a matching Cloudflare Tunnel ingress was observed"
        )

    if access_required:
        if edge_mode == "direct":
            mismatches.append(
                "Cloudflare Access is required while the declared edge mode is direct"
            )
        if not snapshot.configured:
            incomplete.append("Cloudflare Access observation is not configured")
        elif snapshot.access_error:
            incomplete.append("Cloudflare Access observation failed")
        elif not access:
            mismatches.append(
                "Cloudflare Access is required but no matching Access application was observed"
            )
        elif access.get("cloudflare_access_public") is True:
            scope = access.get("cloudflare_access_public_scope") or "unknown"
            mismatches.append(
                f"Cloudflare Access has a broad public/bypass policy at {scope} scope"
            )

    state = "mismatch" if mismatches else "incomplete" if incomplete else "match"
    return {
        "state": state,
        "reasons": mismatches + incomplete,
        "declared": declared,
        "observed": observed,
    }


def enrich_service_exposure(
    rows: list[dict[str, Any]],
    services: Iterable[HomelabService],
    snapshot: CloudflareExposureSnapshot,
) -> list[dict[str, Any]]:
    """Attach sanitized declared-versus-observed exposure evidence to health rows."""
    services_by_id = {service.service_id: service for service in services}
    tunnels = _tunnels_by_hostname(snapshot.tunnels)
    access = _access_by_hostname(snapshot.access_applications)
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        service = services_by_id.get(str(row.get("id") or ""))
        if service is None:
            enriched.append(row)
            continue
        host = _hostname(str(row.get("url") or ""))
        row["exposure"] = _service_exposure(
            service,
            row,
            tunnel=tunnels.get(host or ""),
            access=access.get(host or ""),
            snapshot=snapshot,
        )
        enriched.append(row)
    return enriched
