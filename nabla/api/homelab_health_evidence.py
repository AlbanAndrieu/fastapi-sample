"""Orchestrate multi-source homelab health reconciliation."""

from __future__ import annotations

import asyncio
from typing import Any, Iterable

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_declared import fetch_declared_service_catalog
from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_exposure import enrich_service_exposure, observe_cloudflare_exposure
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import fetch_truenas_runtime, runtime_snapshot_from_health_api
from nabla.api.homelab_service_health import build_reconciled_service_health
from nabla.api.homelab_topology import fetch_homelab_topology
from nabla.api.pfsense_dns_observer import observe_pfsense_dns_posture


def _truenas_internal_hosts(services: Iterable[HomelabService]) -> frozenset[str]:
    return frozenset(
        service.internal_host
        for service in services
        if service.service_id == "truenas" and service.internal_host
    )


async def prepare_homelab_reconciliation_context(
    services: list[HomelabService],
) -> dict[str, Any]:
    """Read independent providers once while service probes are running."""
    declared_task = asyncio.create_task(fetch_declared_service_catalog())
    cloudflare_task = asyncio.create_task(observe_cloudflare_exposure())
    topology_task = asyncio.create_task(fetch_homelab_topology())
    pfsense_dns_task = asyncio.create_task(
        observe_pfsense_dns_posture(
            truenas_hosts=_truenas_internal_hosts(services),
        ),
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
    """Reconcile probes without repeating TrueNAS/Cloudflare/pfSense reads."""
    if context is None:
        services = await fetch_homelab_services()
        context = await prepare_homelab_reconciliation_context(services)
    else:
        services = context["services"]

    declared = context["declared"]
    cloudflare = context["cloudflare"]
    topology = context["topology"]
    pfsense_dns = context["pfsense_dns"]
    cloudflare_summary = cloudflare.summary()

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
        cloudflare_status_confirmed=cloudflare_summary.get("status_confirmed"),
        cloudflare_warning=cloudflare_summary.get("warning"),
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
        "schema_version": 6,
        "services": exposure_aware,
        "truenas_runtime_reachable": runtime.reachable,
        "truenas_runtime_stale": runtime.stale,
        "truenas_runtime_error": runtime.error,
        "cloudflare_configured": cloudflare.configured,
        "cloudflare_tunnels_observed": len(cloudflare.tunnels),
        "cloudflare": cloudflare_summary,
        "pfsense": {"dns": pfsense_dns},
        "reconciliation": {
            "provider_reads_reused": True,
            "truenas_runtime_source": runtime_source,
            "evidence_priority": [
                "truenas_runtime",
                "http_https_tcp",
                "required_dependencies",
                "pfsense",
                "cloudflare",
                "prometheus",
            ],
        },
    }


__all__ = [
    "build_reconciled_service_health",
    "prepare_homelab_reconciliation_context",
    "reconcile_homelab_health_payload",
]
