"""Orchestrate multi-source homelab health reconciliation."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_declared import fetch_declared_service_catalog
from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_exposure import enrich_service_exposure, observe_cloudflare_exposure
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_performance import (
    HOMELAB_HEALTH_PERF_PHASES,
    record_homelab_phase,
    timed_homelab_phase,
)
from nabla.api.homelab_runtime import fetch_truenas_runtime, runtime_snapshot_from_health_api
from nabla.api.homelab_service_health import build_reconciled_service_health
from nabla.api.homelab_topology import fetch_homelab_topology
from nabla.api.pfsense_dns_observer import observe_pfsense_dns_posture


def _truenas_internal_hosts(services: Iterable[HomelabService]) -> frozenset[str]:
    return frozenset(service.internal_host for service in services if service.service_id == "truenas" and service.internal_host)


def _selected_truenas_endpoint_stage(payload: dict[str, Any]) -> dict[str, Any]:
    truenas = payload.get("truenas") if isinstance(payload.get("truenas"), dict) else {}
    diagnostics = truenas.get("diagnostics") if isinstance(truenas.get("diagnostics"), dict) else {}
    public = truenas.get("public") if isinstance(truenas.get("public"), dict) else {}
    configured_url = str(public.get("url") or diagnostics.get("target") or "TrueNAS")
    dns_stage = next(
        (stage for stage in diagnostics.get("stages", []) if isinstance(stage, dict) and stage.get("id") == "dns"),
        {},
    )
    resolved = [str(value) for value in dns_stage.get("resolved", []) if value]
    path_mode = str(diagnostics.get("path_mode") or "public_wan")
    detail_parts = [f"selected endpoint {configured_url}"]
    if resolved:
        detail_parts.append(f"resolved to {', '.join(resolved)}")
    if path_mode == "direct_lan":
        detail_parts.append("direct LAN; hostname retained for TLS/SNI verification")
    else:
        detail_parts.append("public/WAN path")
    return {
        "id": "selected_endpoint",
        "label": "TrueNAS target URL",
        "state": "ok",
        "detail": " · ".join(detail_parts),
        "target_url": configured_url,
        "resolved": resolved,
        "evidence": "runtime_route",
    }


def _pfsense_posture_stage(pfsense_dns: dict[str, Any]) -> dict[str, Any]:
    resolver = pfsense_dns.get("resolver") if isinstance(pfsense_dns.get("resolver"), dict) else {}
    resolver_running = resolver.get("running")
    policy_state = str(pfsense_dns.get("policy_state") or "unknown")
    state = "fail" if policy_state == "fail" or resolver_running is False else "ok" if policy_state == "ok" else "warn"
    if resolver_running is True:
        unbound = "running"
    elif resolver_running is False:
        unbound = "stopped"
    else:
        unbound = "unknown"

    summary = pfsense_dns.get("service_summary") if isinstance(pfsense_dns.get("service_summary"), dict) else {}
    services = pfsense_dns.get("services") if isinstance(pfsense_dns.get("services"), list) else []
    stopped = [str(service.get("identity") or "service") for service in services if isinstance(service, dict) and service.get("runtime_state") == "stopped"]
    unknown = [str(service.get("identity") or "service") for service in services if isinstance(service, dict) and service.get("runtime_state") == "unknown"]
    filters = pfsense_dns.get("security_filters") if isinstance(pfsense_dns.get("security_filters"), list) else []
    filter_text = ", ".join(f"{row.get('label') or row.get('id')}={row.get('state', 'unknown')}" for row in filters if isinstance(row, dict))

    details = [
        "out-of-band posture; pfSense is not on the direct TrueNAS LAN data path",
        f"Unbound={unbound}",
    ]
    if summary:
        details.append(
            f"services running={summary.get('running', 0)} stopped={summary.get('stopped', 0)} unknown={summary.get('unknown', 0)} total={summary.get('total', 0)}",
        )
    if stopped:
        details.append(f"stopped: {', '.join(stopped[:8])}")
    if unknown:
        details.append(f"unknown: {', '.join(unknown[:8])}")
    if filter_text:
        details.append(filter_text)
    if pfsense_dns.get("error_stage"):
        details.append(
            f"partial API evidence: {pfsense_dns['error_stage']} {pfsense_dns.get('error', 'unknown')}",
        )
    return {
        "id": "pfsense_lan_posture",
        "label": "pfSense LAN / DNS posture",
        "state": state,
        "detail": " · ".join(details),
        "evidence": "read_only_pfsense_api",
    }


def _cloudflare_posture_stage(
    cloudflare: dict[str, Any],
    *,
    path_mode: str,
) -> dict[str, Any]:
    confirmed = cloudflare.get("status_confirmed") is True
    configured = cloudflare.get("configured") is True
    tunnels = cloudflare.get("tunnels_observed")
    if confirmed:
        detail = f"Cloudflare inventory confirmed · {tunnels or 0} tunnel(s) observed"
        state = "ok"
    elif not configured:
        detail = "Cloudflare observer not configured; tunnel state is unknown"
        state = "warn"
    else:
        detail = str(
            cloudflare.get("warning") or "Cloudflare tunnel inventory could not be confirmed",
        )
        state = "warn"
    if path_mode == "direct_lan":
        detail += " · observational only; Cloudflare is not on the direct LAN data path"
    return {
        "id": "cloudflare_tunnel_observation",
        "label": "Cloudflare Tunnel observation",
        "state": state,
        "detail": detail,
        "evidence": "cloudflare_control_plane",
    }


def _enrich_truenas_flow(
    payload: dict[str, Any],
    *,
    pfsense_dns: dict[str, Any],
    cloudflare: dict[str, Any],
) -> dict[str, Any]:
    truenas = payload.get("truenas")
    if not isinstance(truenas, dict):
        return payload
    diagnostics = truenas.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return payload

    stages = [dict(stage) for stage in diagnostics.get("stages", []) if isinstance(stage, dict)]
    stages = [
        stage
        for stage in stages
        if stage.get("id")
        not in {
            "selected_endpoint",
            "pfsense_lan_posture",
            "cloudflare_tunnel_observation",
        }
    ]
    stages.insert(0, _selected_truenas_endpoint_stage(payload))

    path_mode = str(diagnostics.get("path_mode") or "public_wan")
    if path_mode == "direct_lan":
        pfsense_stage = _pfsense_posture_stage(pfsense_dns)
        dns_index = next(
            (index for index, stage in enumerate(stages) if stage.get("id") == "dns"),
            0,
        )
        stages.insert(dns_index + 1, pfsense_stage)
    stages.append(_cloudflare_posture_stage(cloudflare, path_mode=path_mode))

    enriched_diagnostics = {**diagnostics, "stages": stages}
    enriched_truenas = {**truenas, "diagnostics": enriched_diagnostics}
    return {**payload, "truenas": enriched_truenas}


async def prepare_homelab_reconciliation_context(
    services: list[HomelabService],
) -> dict[str, Any]:
    """Read independent providers once while service probes are running."""
    timings_ms: dict[str, float] = {}
    declared_task = asyncio.create_task(timed_homelab_phase("declared_catalog", fetch_declared_service_catalog(), timings_ms))
    cloudflare_task = asyncio.create_task(timed_homelab_phase("cloudflare_exposure", observe_cloudflare_exposure(), timings_ms))
    topology_task = asyncio.create_task(timed_homelab_phase("topology", fetch_homelab_topology(), timings_ms))
    pfsense_dns_task = asyncio.create_task(
        timed_homelab_phase(
            "pfsense_posture",
            observe_pfsense_dns_posture(
                truenas_hosts=_truenas_internal_hosts(services),
            ),
            timings_ms,
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
        "performance_phases_ms": timings_ms,
    }


async def reconcile_homelab_health_payload(
    payload: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile probes without repeating TrueNAS/Cloudflare/pfSense reads."""
    reconciliation_started = time.perf_counter()
    if context is None:
        services = await fetch_homelab_services()
        context = await prepare_homelab_reconciliation_context(services)
    else:
        services = context["services"]

    timings_ms = dict(context.get("performance_phases_ms") or {})
    declared = context["declared"]
    cloudflare = context["cloudflare"]
    topology = context["topology"]
    pfsense_dns = context["pfsense_dns"]
    cloudflare_summary = cloudflare.summary()
    payload = _enrich_truenas_flow(
        payload,
        pfsense_dns=pfsense_dns,
        cloudflare=cloudflare_summary,
    )

    checked_at = str(payload.get("checked_at") or "").strip() or None
    truenas = payload.get("truenas")
    api_result = truenas.get("api") if isinstance(truenas, dict) else None
    runtime_started = time.perf_counter()
    runtime = runtime_snapshot_from_health_api(
        api_result if isinstance(api_result, dict) else None,
        observed_at=checked_at,
    )
    runtime_source = "health_api"
    if runtime is None:
        runtime = await fetch_truenas_runtime()
        runtime_source = "runtime_fallback"
    record_homelab_phase(
        timings_ms,
        "truenas_runtime",
        time.perf_counter() - runtime_started,
    )

    runtime_bindings = {service.service_id: service.runtime for service in declared.services if service.runtime is not None}
    public_results = [dict(row) for row in payload.get("services", []) if isinstance(row, dict)]
    internal_results = [dict(row) for row in payload.get("internal_services", []) if isinstance(row, dict)]
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
    record_homelab_phase(
        timings_ms,
        "reconciliation",
        time.perf_counter() - reconciliation_started,
    )
    performance_phases = {phase: timings_ms.get(phase) for phase in HOMELAB_HEALTH_PERF_PHASES if phase != "total"}
    return {
        **payload,
        "schema_version": 6,
        "performance": {
            "phases_ms": performance_phases,
            "fixed_cardinality": True,
            "phase_count": len(HOMELAB_HEALTH_PERF_PHASES),
        },
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
