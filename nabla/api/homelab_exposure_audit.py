"""Compare reviewed homelab exposure policy with observed Cloudflare Tunnel ingress."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Literal
from urllib.parse import urlsplit

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_tunnels,
)
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService

ExposureFindingState = Literal[
    "MATCH",
    "UNEXPECTEDLY_EXPOSED",
    "MISSING_EXPOSURE",
    "UNKNOWN",
]
AuditStatus = Literal["ok", "warn", "fail", "disabled", "error"]


def _cloudflare_candidate_hostname(service: HomelabService) -> str | None:
    """Return a hostname when a catalog URL plausibly represents Cloudflare ingress."""
    if not service.tunnel_url:
        return None
    try:
        parsed = urlsplit(service.tunnel_url)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.port not in (None, 443):
        return None
    host = parsed.hostname.lower().rstrip(".")
    if host.endswith(".int.albandrieu.com"):
        return None
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return None
    return host


def _observed_ingress_by_hostname(
    observations: list[CloudflareTunnelObservation],
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    by_hostname: dict[str, list[dict[str, Any]]] = {}
    has_unknown_local_config = False
    for tunnel in observations:
        if tunnel.config_source != "cloudflare":
            has_unknown_local_config = True
        for ingress in tunnel.ingress:
            host = ingress.hostname.lower().rstrip(".")
            by_hostname.setdefault(host, []).append(
                {
                    "tunnel_id": ingress.tunnel_id,
                    "tunnel_name": ingress.tunnel_name,
                    "tunnel_status": ingress.status,
                    "service": ingress.service,
                }
            )
    return by_hostname, has_unknown_local_config


def _finding_for_service(
    service: HomelabService,
    hostname: str,
    routes: list[dict[str, Any]],
    *,
    observations_authoritative: bool,
) -> dict[str, Any]:
    observed = bool(routes)
    if not observations_authoritative and not observed:
        state: ExposureFindingState = "UNKNOWN"
    elif service.external and observed:
        state = "MATCH"
    elif service.external and not observed:
        state = "MISSING_EXPOSURE"
    elif not service.external and observed:
        state = "UNEXPECTEDLY_EXPOSED"
    else:
        state = "MATCH"

    return {
        "id": service.service_id,
        "name": service.name,
        "hostname": hostname,
        "desired_external": service.external,
        "observed_exposed": observed,
        "state": state,
        "routes": routes,
    }


def build_exposure_audit_payload(
    services: list[HomelabService],
    observations: list[CloudflareTunnelObservation],
    *,
    configured: bool,
    observer_error: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic desired-vs-observed exposure audit payload."""
    observed_by_hostname, has_unknown_local_config = _observed_ingress_by_hostname(
        observations
    )
    observations_authoritative = (
        configured and observer_error is None and not has_unknown_local_config
    )

    desired_by_hostname: dict[str, HomelabService] = {}
    findings: list[dict[str, Any]] = []
    for service in services:
        hostname = _cloudflare_candidate_hostname(service)
        if hostname is None:
            continue
        desired_by_hostname[hostname] = service
        findings.append(
            _finding_for_service(
                service,
                hostname,
                observed_by_hostname.get(hostname, []),
                observations_authoritative=observations_authoritative,
            )
        )

    for hostname, routes in observed_by_hostname.items():
        if hostname in desired_by_hostname:
            continue
        findings.append(
            {
                "id": None,
                "name": "Unmanaged Cloudflare hostname",
                "hostname": hostname,
                "desired_external": None,
                "observed_exposed": True,
                "state": "UNEXPECTEDLY_EXPOSED",
                "routes": routes,
            }
        )

    findings.sort(key=lambda item: (str(item["state"]), str(item["hostname"])))
    counts = Counter(str(item["state"]) for item in findings)

    if not configured:
        status: AuditStatus = "disabled"
    elif observer_error is not None:
        status = "error"
    elif counts["UNEXPECTEDLY_EXPOSED"]:
        status = "fail"
    elif counts["MISSING_EXPOSURE"] or counts["UNKNOWN"]:
        status = "warn"
    else:
        status = "ok"

    return {
        "schema_version": 1,
        "status": status,
        "configured": configured,
        "authoritative": observations_authoritative,
        "has_unknown_local_config": has_unknown_local_config,
        "observer_error": observer_error,
        "summary": {
            "match": counts["MATCH"],
            "unexpectedly_exposed": counts["UNEXPECTEDLY_EXPOSED"],
            "missing_exposure": counts["MISSING_EXPOSURE"],
            "unknown": counts["UNKNOWN"],
        },
        "findings": findings,
    }


async def audit_homelab_exposure() -> dict[str, Any]:
    """Observe Cloudflare read-only state and compare it with the reviewed catalog."""
    services = await fetch_homelab_services()
    configured = CloudflareTunnelSettings.from_environment() is not None
    if not configured:
        return build_exposure_audit_payload(services, [], configured=False)

    try:
        observations = await asyncio.to_thread(observe_cloudflare_tunnels)
    except Exception as exc:
        return build_exposure_audit_payload(
            services,
            [],
            configured=True,
            observer_error=(str(exc).strip() or exc.__class__.__name__)[:500],
        )
    return build_exposure_audit_payload(services, observations, configured=True)
