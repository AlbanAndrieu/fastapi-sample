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

_DIRECT_EXTERNAL_SUFFIX = ".int.albandrieu.com"


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _origin_host_port(url: str | None) -> tuple[str | None, int | None]:
    if not url:
        return None, None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".") or None
        port = parsed.port
    except ValueError:
        return None, None
    if port is None:
        port = {"http": 80, "https": 443}.get(parsed.scheme.lower())
    return host, port


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
                "cloudflare_tunnel_config_source": tunnel.config_source,
                "cloudflare_origin_service": ingress.service,
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
    elif access.get("cloudflare_access_policy_count") == 0:
        mismatches.append(
            "Cloudflare Access application is observed but contains no policy",
        )
    elif access.get("cloudflare_access_public") is True:
        scope = access.get("cloudflare_access_public_scope") or "unknown"
        mismatches.append(
            f"Cloudflare Access has a broad public/bypass policy at {scope} scope",
        )
    return mismatches, incomplete


def _origin_reconciliation(
    service: HomelabService,
    tunnel: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    expected_host = (service.internal_host or "").lower().rstrip(".") or None
    expected_port = service.internal_port
    observed_service = (
        str(tunnel.get("cloudflare_origin_service") or "") if tunnel else ""
    )
    observed_host, observed_port = _origin_host_port(observed_service)
    comparable = bool(expected_host and expected_port and observed_host and observed_port)
    matches = (
        expected_host == observed_host and expected_port == observed_port
        if comparable
        else None
    )
    detail = {
        "cloudflare_origin_service": observed_service or None,
        "cloudflare_origin_host": observed_host,
        "cloudflare_origin_port": observed_port,
        "topology_internal_host": expected_host,
        "topology_internal_port": expected_port,
        "cloudflare_origin_matches_topology": matches,
    }
    if matches is False:
        warning = (
            f"⚠️ Cloudflare origin {observed_host}:{observed_port} does not match "
            f"topology {expected_host}:{expected_port}"
        )
        return detail, warning
    return detail, None


def _unique_reasons(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for reason in group:
            normalized = reason.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _declared_risk_reasons(
    service: HomelabService,
    *,
    tunnel: dict[str, Any] | None,
) -> list[str]:
    if not service.external or service.endpoint_enabled is False:
        return []
    host = _hostname(service.tunnel_url) or ""
    reasons: list[str] = []
    if service.tunnel_secure is False:
        if host.endswith(_DIRECT_EXTERNAL_SUFFIX):
            reasons.append(
                "External *.int.albandrieu.com endpoint bypasses Cloudflare Tunnel/Access and is directly exposed",
            )
        else:
            reasons.append(
                "Direct external exposure bypasses Cloudflare Tunnel/Access",
            )
    if service.tunnel_secure is True and not service.effective_cloudflare_access_required:
        suffix = " with an observed Tunnel ingress" if tunnel else ""
        reasons.append(
            f"external=true declares a Cloudflare edge{suffix} but Cloudflare Access is disabled; anonymous exposure may be possible",
        )
    return reasons


def _control_plane_risk_reasons(
    service: HomelabService,
    snapshot: CloudflareExposureSnapshot,
) -> tuple[list[str], list[str]]:
    if not service.external or not service.effective_cloudflare_access_required:
        return [], []
    if not snapshot.configured:
        return [
            "Cloudflare account observation is not configured; required Access and Service Auth posture cannot be verified",
        ], []
    if snapshot.stale or snapshot.access_error:
        return [], [
            "Cloudflare Access control-plane evidence is temporarily unverified",
        ]

    control = snapshot.access_control_plane
    if control is None:
        return [], [
            "Project-scoped Cloudflare Access policy and Service Token inventory is unavailable",
        ]

    confirmed: list[str] = []
    unconfirmed: list[str] = []
    if control.reusable_policy_error:
        unconfirmed.append(
            "Project-scoped reusable Access policy inventory could not be confirmed",
        )
    else:
        if control.reusable_policy_count == 0:
            confirmed.append("Project-scoped reusable Access policy is missing")
        elif control.reusable_policy_app_count == 0:
            confirmed.append(
                "Project-scoped reusable Access policy exists but is not assigned to an Access application",
            )

    if control.service_token_error:
        unconfirmed.append(
            "Project-scoped Cloudflare Service Token inventory could not be confirmed",
        )
    else:
        if control.service_token_count == 0:
            confirmed.append("Project-scoped Cloudflare Service Token is missing")
        elif control.service_token_enabled_count == 0:
            confirmed.append(
                "Project-scoped Cloudflare Service Token exists but no token is enabled",
            )
        if control.configured_service_token_present is False:
            confirmed.append(
                "Configured Service Auth client does not match the project-scoped Cloudflare Service Token",
            )
    return confirmed, unconfirmed


def _unexpected_private_exposure_reasons(
    service: HomelabService,
    *,
    tunnel: dict[str, Any] | None,
    access: dict[str, Any] | None,
) -> list[str]:
    if service.external and service.endpoint_enabled is not False:
        return []
    reasons: list[str] = []
    if tunnel:
        reasons.append(
            "Service is not declared external but a Cloudflare Tunnel ingress is observed",
        )
    if access:
        reasons.append(
            "Service is not declared external but a Cloudflare Access application is observed",
        )
    return reasons


def _risk_state(
    *,
    confirmed: Iterable[str],
    unconfirmed: Iterable[str],
) -> str:
    if any(confirmed):
        return "at_risk"
    if any(unconfirmed):
        return "unknown"
    return "none"


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
    origin, origin_warning = _origin_reconciliation(service, tunnel)
    observed = {
        "public_https_reachable": (bool(row.get("reachable")) if row.get("http_status", 0) or row.get("reachable") else None),
        "cloudflare_tunnel_observed": bool(tunnel),
        "cloudflare_tunnel_name": tunnel.get("cloudflare_tunnel_name") if tunnel else None,
        "cloudflare_tunnel_status": (tunnel.get("cloudflare_tunnel_status") if tunnel else None),
        "cloudflare_tunnel_config_source": (tunnel.get("cloudflare_tunnel_config_source") if tunnel else None),
        **origin,
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
        "internal_host": service.internal_host,
        "internal_port": service.internal_port,
    }

    private_exposure = _unexpected_private_exposure_reasons(
        service,
        tunnel=tunnel,
        access=access,
    )
    if not service.external or service.endpoint_enabled is False:
        return {
            "state": "mismatch" if private_exposure else "not_applicable",
            "reasons": private_exposure,
            "risk_state": "at_risk" if private_exposure else "none",
            "risk_reasons": private_exposure,
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
    if origin_warning:
        mismatches.append(origin_warning)
    incomplete = edge_incomplete + access_incomplete

    declared_risk = _declared_risk_reasons(service, tunnel=tunnel)
    control_risk, control_unknown = _control_plane_risk_reasons(service, snapshot)
    confirmed_risk = _unique_reasons(mismatches, declared_risk, control_risk)
    unconfirmed_risk = _unique_reasons(incomplete, control_unknown)
    risk_reasons = _unique_reasons(confirmed_risk, unconfirmed_risk)

    return {
        "state": ("mismatch" if mismatches else "incomplete" if incomplete else "match"),
        "reasons": mismatches + incomplete,
        "risk_state": _risk_state(
            confirmed=confirmed_risk,
            unconfirmed=unconfirmed_risk,
        ),
        "risk_reasons": risk_reasons,
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
    """Attach edge evidence and security risk without changing application health."""
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
        exposure = _service_exposure(
            service,
            row,
            tunnel=tunnels.get(host or ""),
            access=access.get(host or ""),
            snapshot=snapshot,
        )
        row["exposure"] = exposure
        row["risk_state"] = exposure["risk_state"]
        row["risk_reasons"] = exposure["risk_reasons"]
        enriched.append(row)
    return enriched


__all__ = [
    "CloudflareExposureSnapshot",
    "enrich_service_exposure",
    "observe_cloudflare_exposure",
]
