"""Orchestrate homelab provider reads and service-health reconciliation."""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_declared import (
    DeclaredServiceCatalog,
    fetch_declared_service_catalog,
)
from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_exposure import enrich_service_exposure, observe_cloudflare_exposure
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import (
    fetch_truenas_runtime,
    runtime_snapshot_from_health_api,
)
from nabla.api.homelab_service_health import build_reconciled_service_health
from nabla.api.homelab_topology import fetch_homelab_topology
from nabla.api.pfsense_dns_observer import observe_pfsense_dns_posture

__all__ = ["build_reconciled_service_health", "reconcile_homelab_health_payload"]


def _truenas_internal_hosts(services: Iterable[HomelabService]) -> frozenset[str]:
    return frozenset(
        service.internal_host
        for service in services
        if service.service_id == "truenas" and service.internal_host
    )


def _supplement_declared_runtime_services(
    services: list[HomelabService],
    declared: DeclaredServiceCatalog,
) -> list[HomelabService]:
    """Add code-owned TrueNAS workloads missing from the legacy probe catalog.

    The generated x-nabla catalog is authoritative for workload identity. Added
    rows are runtime-only here: endpoint probing still requires explicit health
    targets in the probe catalog, so discovering a URL can never create exposure.
    """
    supplemented = list(services)
    existing = {service.service_id for service in supplemented}
    for item in declared.services:
        runtime = item.runtime
        if item.service_id in existing or runtime is None:
            continue
        if runtime.provider != "truenas-app" or item.presentation_role is None:
            continue
        supplemented.append(
            HomelabService(
                id=item.service_id,
                name=item.name,
                description=item.description,
                tunnelUrl=item.url,
                external=False,
                sourceId=item.compose_service,
                healthNote=(
                    "Runtime discovered from generated x-nabla catalog; "
                    "functional endpoint probe not declared."
                ),
            )
        )
        existing.add(item.service_id)
    return supplemented


async def prepare_homelab_reconciliation_context(
    services: list[HomelabService],
) -> dict[str, Any]:
    """Start independent provider/catalog reads while service probes are running."""
    declared_task = asyncio.create_task(fetch_declared_service_catalog())
    cloudflare_task = asyncio.create_task(observe_cloudflare_exposure())
    topology_task = asyncio.create_task(fetch_homelab_topology())
    pfsense_dns_task = asyncio.create_task(
        observe_pfsense_dns_posture(
            truenas_hosts=_truenas_internal_hosts(services),
        )
    )
    declared, cloudflare, topology, pfsense_dns = await asyncio.gather(
        declared_task,
        cloudflare_task,
        topology_task,
        pfsense_dns_task,
    )
    return {
        "services": services,
        "declared": declared,
        "cloudflare": cloudflare,
        "topology": topology,
        "pfsense_dns": pfsense_dns,
    }


async def reconcile_homelab_health_payload(
    payload: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile probes in evidence-precedence order without duplicate reads.

    TrueNAS runtime is the primary workload source. HTTP/HTTPS/TCP results prove
    endpoint availability. pfSense and Cloudflare are path/control evidence and
    cannot turn provider uncertainty into an application failure. Prometheus
    remains supporting telemetry and is consumed separately by platform metrics.
    """
    if context is None:
        services = await fetch_homelab_services()
        context = await prepare_homelab_reconciliation_context(services)
    else:
        services = list(context["services"])

    declared = context["declared"]
    cloudflare = context["cloudflare"]
    topology = context["topology"]
    pfsense_dns = context["pfsense_dns"]
    services = _supplement_declared_runtime_services(services, declared)

    checked_at = str(payload.get("checked_at") or "").strip() or None
    truenas = payload.get("truenas")
    api_result = truenas.get("api") if isinstance(truenas, dict) else None
    runtime = runtime_snapshot_from_health_api(
        api_result if isinstance(api_result, dict) else None,
        observed_at=checked_at,
    )
    runtime_source = "health_api"
    if runtime is None:
        runtime = await fetch_truenas_runtime()
        runtime_source = "runtime_fallback"

    runtime_bindings = {
        service.service_id: service.runtime
        for service in declared.services
        if service.runtime is not None
    }
    public_results = [
        dict(row) for row in payload.get("services", []) if isinstance(row, dict)
    ]
    internal_results = [
        dict(row)
        for row in payload.get("internal_services", [])
        if isinstance(row, dict)
    ]
    reconciled = build_reconciled_service_health(
        services,
        public_results=public_results,
        internal_results=internal_results,
        runtime=runtime,
        tunnels=cloudflare.tunnels,
        runtime_bindings=runtime_bindings,
        cloudflare_stale=cloudflare.stale,
        checked_at=checked_at,
    )
    dependency_aware = propagate_required_dependency_health(reconciled, topology)
    exposure_aware = enrich_service_exposure(
        dependency_aware,
        services,
        cloudflare,
    )
    return {
        **payload,
        "schema_version": 7,
        "services": exposure_aware,
        "truenas_runtime_reachable": runtime.reachable,
        "truenas_runtime_stale": runtime.stale,
        "truenas_runtime_error": runtime.error,
        "cloudflare_configured": cloudflare.configured,
        "cloudflare_tunnels_observed": len(cloudflare.tunnels),
        "cloudflare": cloudflare.summary(),
        "pfsense": {"dns": pfsense_dns},
        "reconciliation": {
            "provider_reads_reused": True,
            "truenas_runtime_source": runtime_source,
            "legacy_probe_services": len(context["services"]),
            "reconciled_services": len(services),
            "evidence_precedence": [
                "truenas-runtime",
                "http-https-tcp",
                "pfsense-path",
                "cloudflare-edge",
                "prometheus-telemetry",
            ],
        },
    }
