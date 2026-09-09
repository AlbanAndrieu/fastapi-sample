"""Reconcile direct, TrueNAS runtime and Cloudflare ingress health evidence."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from nabla.api.cloudflare_tunnels import CloudflareTunnelObservation
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_declared import RuntimeBinding, fetch_declared_service_catalog
from nabla.api.homelab_dependency_health import propagate_required_dependency_health
from nabla.api.homelab_exposure import enrich_service_exposure, observe_cloudflare_exposure
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import (
    ObservedApp,
    TrueNASRuntimeSnapshot,
    fetch_truenas_runtime,
    match_runtime_binding,
    runtime_snapshot_from_health_api,
)
from nabla.api.homelab_topology import fetch_homelab_topology
from nabla.api.pfsense_dns_observer import observe_pfsense_dns_posture

HealthState = str
_RUNNING_APP_STATES = frozenset({"ACTIVE", "HEALTHY", "RUNNING", "STARTED", "UP"})
_DOWN_APP_STATES = frozenset(
    {"CRASHED", "DEPLOYING", "DOWN", "ERROR", "FAILED", "STOPPED", "STOPPING"},
)
_HEALTHY_TUNNEL_STATES = frozenset({"ACTIVE", "HEALTHY", "OK", "UP"})
_DOWN_TUNNEL_STATES = frozenset({"DOWN", "FAILED", "INACTIVE"})
_KEY_RE = re.compile(r"[^a-z0-9]+")


def _key(value: str | None) -> str:
    return _KEY_RE.sub("-", (value or "").strip().lower()).strip("-")


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _normalized_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return url.rstrip("/") + "/"


def _observation_age_seconds(observed_at: str | None) -> int | None:
    if not observed_at:
        return None
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    return max(0, int(age))


def _runtime_app_for_service(
    service: HomelabService,
    runtime: TrueNASRuntimeSnapshot | None,
    binding: RuntimeBinding | None = None,
) -> ObservedApp | None:
    if runtime is None or not runtime.reachable:
        return None

    if binding is not None and binding.provider == "truenas-app":
        matches = [app for app in runtime.apps if match_runtime_binding(app, binding)[0]]
        return matches[0] if len(matches) == 1 else None

    # Legacy presentation-only entries retain the old bounded heuristic until
    # their code-owned x-nabla runtime binding exists.
    candidates = {
        candidate
        for candidate in (
            _key(service.source_id),
            _key(service.service_id),
            _key(service.name),
        )
        if candidate
    }
    if not candidates:
        return None
    matches = [app for app in runtime.apps if candidates.intersection({_key(app.app_id), _key(app.name)})]
    return matches[0] if len(matches) == 1 else None


def _runtime_state(app: ObservedApp | None) -> HealthState | None:
    if app is None:
        return None
    state = app.state.strip().upper()
    if state in _RUNNING_APP_STATES:
        return "ok"
    if state in _DOWN_APP_STATES:
        return "fail"
    return "warn"


def _tunnel_state(status: str | None) -> HealthState | None:
    normalized = (status or "").strip().upper()
    if not normalized:
        return None
    if normalized in _HEALTHY_TUNNEL_STATES:
        return "ok"
    if normalized in _DOWN_TUNNEL_STATES:
        return "fail"
    return "warn"


def _tunnel_by_hostname(observations: Iterable[CloudflareTunnelObservation]) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for tunnel in observations:
        for ingress in tunnel.ingress:
            result[ingress.hostname.lower().rstrip(".")] = {
                "tunnel_status": ingress.status or tunnel.status,
                "tunnel_name": ingress.tunnel_name or tunnel.name,
            }
    return result


def _state_from_direct_evidence(
    *,
    direct: HealthState | None,
    internal: HealthState | None,
    runtime: HealthState | None,
    tunnel: HealthState | None,
) -> HealthState | None:
    if direct == "ok":
        if tunnel == "fail":
            return "warn" if "ok" in {internal, runtime} else "fail"
        return "warn" if internal == "fail" else "ok"

    if direct == "warn":
        if tunnel == "fail":
            return "warn" if "ok" in {internal, runtime} else "fail"
        return "warn"

    if direct == "fail":
        # A running origin with a broken public path is degraded. Tunnel health
        # alone must never rescue a failed application probe.
        return "warn" if "ok" in {internal, runtime} else "fail"

    return None


def _state_without_direct_evidence(
    *,
    internal: HealthState | None,
    runtime: HealthState | None,
    tunnel: HealthState | None,
    external: bool,
) -> HealthState:
    if internal == "ok":
        return "ok"
    if internal == "fail":
        return "warn" if runtime == "ok" else "fail"
    if runtime == "ok":
        # A private service can be healthy even when the current observer cannot
        # perform its functional LAN probe. Public reachability is not expected.
        return "warn" if external else "ok"

    # Missing/down Cloudflare exposure is a configuration degradation when no
    # stronger application failure has been observed.
    if tunnel in {"ok", "fail", "warn"}:
        return "warn"
    if any(state is not None for state in (internal, runtime, tunnel)):
        return "warn"
    return "unknown"


def _reconciled_state(
    *,
    direct: HealthState | None,
    internal: HealthState | None,
    runtime: HealthState | None,
    tunnel: HealthState | None,
    external: bool,
    direct_http_status: int = 0,
    application_error: bool = False,
    runtime_missing: bool = False,
) -> HealthState:
    """Classify service availability without letting edge evidence mask downtime.

    Runtime STOPPED/FAILED is authoritative when it is fresh. A healthy
    Cloudflare tunnel only proves the edge connector is connected; it does not
    prove the origin application is serving traffic.
    """
    origin_proven_up = internal == "ok" or 200 <= direct_http_status < 300

    if runtime_missing:
        return "warn" if origin_proven_up else "fail"
    if application_error:
        return "warn"
    if runtime == "fail":
        return "warn" if origin_proven_up else "fail"

    direct_state = _state_from_direct_evidence(
        direct=direct,
        internal=internal,
        runtime=runtime,
        tunnel=tunnel,
    )
    if direct_state is not None:
        return direct_state

    return _state_without_direct_evidence(
        internal=internal,
        runtime=runtime,
        tunnel=tunnel,
        external=external,
    )


def _observation_freshness(
    *,
    checked_at: str | None,
    direct_result: dict[str, Any] | None,
    internal_result: dict[str, Any] | None,
    runtime: TrueNASRuntimeSnapshot | None,
    app: ObservedApp | None,
    tunnel_evidence: dict[str, str | None] | None,
) -> tuple[str | None, int | None, bool]:
    has_fresh_probe = direct_result is not None or internal_result is not None or tunnel_evidence is not None
    if has_fresh_probe:
        return checked_at, _observation_age_seconds(checked_at), False
    if runtime is not None and app is not None:
        return runtime.observed_at, _observation_age_seconds(runtime.observed_at), runtime.stale
    return None, None, False


def build_reconciled_service_health(
    services: list[HomelabService],
    *,
    public_results: list[dict[str, Any]],
    internal_results: list[dict[str, Any]],
    runtime: TrueNASRuntimeSnapshot | None,
    tunnels: Iterable[CloudflareTunnelObservation],
    runtime_bindings: Mapping[str, RuntimeBinding] | None = None,
    cloudflare_stale: bool = False,
    checked_at: str | None = None,
) -> list[dict[str, Any]]:
    direct_by_url = {normalized: result for result in public_results if (normalized := _normalized_url(str(result.get("url") or ""))) is not None}
    internal_by_id = {str(result.get("id")): result for result in internal_results if result.get("id")}
    tunnels_by_host = _tunnel_by_hostname(tunnels)
    rows: list[dict[str, Any]] = []
    for service in services:
        endpoint_url = service.effective_endpoint_url
        url = _normalized_url(endpoint_url)
        direct_result = direct_by_url.get(url) if url is not None else None
        internal_result = internal_by_id.get(service.service_id)
        binding = (runtime_bindings or {}).get(service.service_id)
        app = _runtime_app_for_service(service, runtime, binding)
        runtime_health = None if runtime is not None and runtime.stale else _runtime_state(app)
        runtime_missing = bool(
            binding is not None and binding.provider == "truenas-app" and runtime is not None and runtime.reachable and not runtime.stale and app is None,
        )
        host = _hostname(endpoint_url)
        tunnel_evidence = tunnels_by_host.get(host or "")
        tunnel_status = str(tunnel_evidence.get("tunnel_status")) if tunnel_evidence and tunnel_evidence.get("tunnel_status") is not None else None
        tunnel_health = None if cloudflare_stale else _tunnel_state(tunnel_status)
        direct_health = str(direct_result.get("state")) if direct_result is not None else None
        internal_health = str(internal_result.get("state")) if internal_result is not None else None
        application_error = str(direct_result.get("application_error")) if direct_result is not None and direct_result.get("application_error") else None
        reconciled_state = _reconciled_state(
            direct=direct_health,
            internal=internal_health,
            runtime=runtime_health,
            tunnel=tunnel_health,
            external=service.external,
            direct_http_status=(int(direct_result.get("http_status", 0)) if direct_result is not None else 0),
            application_error=application_error is not None,
            runtime_missing=runtime_missing,
        )
        observed_at, observation_age_seconds, observation_stale = _observation_freshness(
            checked_at=checked_at,
            direct_result=direct_result,
            internal_result=internal_result,
            runtime=runtime,
            app=app,
            tunnel_evidence=tunnel_evidence,
        )
        row: dict[str, Any] = {
            "id": service.service_id,
            "name": service.name,
            "url": url or endpoint_url,
            "url_derived": service.tunnel_url is None,
            "reachable": bool(direct_result and direct_result.get("reachable")),
            "http_status": int(direct_result.get("http_status", 0)) if direct_result else 0,
            "state": reconciled_state,
            "tls_trusted": direct_result.get("tls_trusted") if direct_result else None,
            "direct_state": direct_health,
            "internal_state": internal_health,
            "direct_probe_source": (direct_result.get("probe_source") if direct_result is not None else None),
            "direct_probe_observed_at": (direct_result.get("probe_observed_at") if direct_result is not None else None),
            "direct_probe_age_seconds": (direct_result.get("probe_age_seconds") if direct_result is not None else None),
            "direct_probe_refresh_error": (direct_result.get("probe_refresh_error") if direct_result is not None else None),
            "internal_probe_source": (internal_result.get("probe_source") if internal_result is not None else None),
            "internal_probe_observed_at": (internal_result.get("probe_observed_at") if internal_result is not None else None),
            "internal_probe_age_seconds": (internal_result.get("probe_age_seconds") if internal_result is not None else None),
            "internal_probe_refresh_error": (internal_result.get("probe_refresh_error") if internal_result is not None else None),
            "runtime_state": app.state if app is not None else None,
            "runtime_app": app.app_id if app is not None else None,
            "runtime_reachable": runtime.reachable if runtime is not None else None,
            "runtime_missing": runtime_missing,
            "observed_at": observed_at,
            "observation_age_seconds": observation_age_seconds,
            "observation_stale": observation_stale,
        }
        if service.health_note:
            row["health_note"] = service.health_note
        if runtime is not None:
            row["runtime_stale"] = runtime.stale
        if tunnel_evidence is not None:
            row["tunnel_stale"] = cloudflare_stale
        if direct_result is not None:
            for key in ("latency_ms", "error", "application_error"):
                if key in direct_result:
                    row[key] = direct_result[key]
        if tunnel_evidence is not None:
            row.update(tunnel_evidence)
        rows.append(row)
    return rows


def _truenas_internal_hosts(services: Iterable[HomelabService]) -> frozenset[str]:
    return frozenset(service.internal_host for service in services if service.service_id == "truenas" and service.internal_host)


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
    """Reconcile probe evidence without repeating already-completed provider reads."""
    if context is None:
        services = await fetch_homelab_services()
        context = await prepare_homelab_reconciliation_context(services)
    else:
        services = context["services"]

    declared = context["declared"]
    cloudflare = context["cloudflare"]
    topology = context["topology"]
    pfsense_dns = context["pfsense_dns"]

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
        "cloudflare": cloudflare.summary(),
        "pfsense": {"dns": pfsense_dns},
        "reconciliation": {
            "provider_reads_reused": True,
            "truenas_runtime_source": runtime_source,
        },
    }
