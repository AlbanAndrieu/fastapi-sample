"""Sanitized declared-versus-observed Cloudflare exposure reconciliation."""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlsplit

from nabla.api.cloudflare_exposure_observer import (
    CloudflareExposureSnapshot,
    observe_cloudflare_exposure,
)
from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareTunnelObservation,
)
from nabla.api.homelab_models import HomelabService


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
                public = decision == "bypass" or (decision == "allow" and policy.includes_everyone)
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
            "cloudflare_access_public_scope": ("host" if "host" in public_scopes else "path" if "path" in public_scopes else None),
        }
    return result


def _declared_edge_mode(service: HomelabService) -> str:
    if service.tunnel_secure is True:
        return "cloudflare"
    if service.tunnel_secure is False:
        return "direct"
    return "unspecified"


def _has_local_managed_tunnels(snapshot: CloudflareExposureSnapshot) -> bool:
    """Return whether remote API ingress matching is incomplete by construction."""
    return any(tunnel.config_source == "local" for tunnel in snapshot.tunnels)


def _edge_reasons(
    edge_mode: str,
    tunnel: dict[str, Any] | None,
    snapshot: CloudflareExposureSnapshot,
) -> tuple[list[str], list[str]]:
    mismatches: list[str] = []
    incomplete: list[str] = []
    if edge_mode == "unspecified":
        incomplete.append("External service has no explicit edge-mode declaration")
    elif edge_mode == "cloudflare":
        if not snapshot.configured:
            incomplete.append("Cloudflare observation is not configured")
        elif snapshot.tunnel_error or snapshot.stale:
            incomplete.append("⚠️ Cloudflare global status could not be confirmed")
        elif not tunnel and _has_local_managed_tunnels(snapshot):
            incomplete.append(
                "Cloudflare Tunnel uses local configuration; matching ingress cannot be verified through the remote configuration API",
            )
        elif not tunnel:
            mismatches.append(
                "Cloudflare edge is declared but no matching Tunnel ingress was observed",
            )
    elif tunnel:
        mismatches.append(
            "Direct exposure is declared but a matching Cloudflare Tunnel ingress was observed",
        )
    return mismatches, incomplete


def _access_reasons(
    *,
    access_required: bool,
    edge_mode: str,
    access: dict[str, Any] | None,
    snapshot: CloudflareExposureSnapshot,
) -> tuple[list[str], list[str]]:
    if not access_required:
        return [], []
    mismatches: list[str] = []
    incomplete: list[str] = []
    if edge_mode == "direct":
        mismatches.append(
            "Cloudflare Access is required while the declared edge mode is direct",
        )
    if not snapshot.configured:
        incomplete.append("Cloudflare Access observation is not configured")
    elif snapshot.access_error or snapshot.stale:
        incomplete.append("⚠️ Cloudflare Access status could not be confirmed")
    elif not access:
        mismatches.append(
            "Cloudflare Access is required but no matching Access application was observed",
        )
    elif access.get("cloudflare_access_public") is True:
        scope = access.get("cloudflare_access_public_scope") or "unknown"
        mismatches.append(
            f"Cloudflare Access has a broad public/bypass policy at {scope} scope",
        )
    return mismatches, incomplete


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
    observed = {
        "public_https_reachable": (bool(row.get("reachable")) if row.get("http_status", 0) or row.get("reachable") else None),
        "cloudflare_tunnel_observed": bool(tunnel),
        "cloudflare_tunnel_name": tunnel.get("cloudflare_tunnel_name") if tunnel else None,
        "cloudflare_tunnel_status": tunnel.get("cloudflare_tunnel_status") if tunnel else None,
        "cloudflare_access_observed": bool(access),
        "cloudflare_access_application_count": (access.get("cloudflare_access_application_count") if access else 0),
        "cloudflare_access_policy_count": (access.get("cloudflare_access_policy_count") if access else 0),
        "cloudflare_access_policy_decisions": (access.get("cloudflare_access_policy_decisions") if access else []),
        "cloudflare_access_public": (access.get("cloudflare_access_public") if access else None),
        "cloudflare_access_public_scope": (access.get("cloudflare_access_public_scope") if access else None),
        "cloudflare_access_public_policy_count": (access.get("cloudflare_access_public_policy_count") if access else 0),
    }
    declared = {
        "external": service.external,
        "endpoint_enabled": service.endpoint_enabled,
        "edge_mode": edge_mode,
        "cloudflare_access_required": access_required,
        "security_exception_declared": bool(service.security_exception),
    }
    if not service.external or service.endpoint_enabled is False:
        return {
            "state": "not_applicable",
            "reasons": [],
            "declared": declared,
            "observed": observed,
        }

    edge_mismatch, edge_incomplete = _edge_reasons(edge_mode, tunnel, snapshot)
    access_mismatch, access_incomplete = _access_reasons(
        access_required=access_required,
        edge_mode=edge_mode,
        access=access,
        snapshot=snapshot,
    )
    mismatches = edge_mismatch + access_mismatch
    incomplete = edge_incomplete + access_incomplete
    return {
        "state": "mismatch" if mismatches else "incomplete" if incomplete else "match",
        "reasons": mismatches + incomplete,
        "declared": declared,
        "observed": observed,
        "provider_status_confirmed": snapshot.summary()["status_confirmed"],
        "provider_warning": snapshot.summary()["warning"],
    }


def enrich_service_exposure(
    rows: list[dict[str, Any]],
    services: Iterable[HomelabService],
    snapshot: CloudflareExposureSnapshot,
) -> list[dict[str, Any]]:
    """Attach edge evidence without changing application health state."""
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


__all__ = [
    "CloudflareExposureSnapshot",
    "enrich_service_exposure",
    "observe_cloudflare_exposure",
]
