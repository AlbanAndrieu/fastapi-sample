"""Pure service-level reconciliation for homelab health evidence."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from nabla.api.cloudflare_tunnels import CloudflareTunnelObservation
from nabla.api.homelab_declared import RuntimeBinding
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot, match_runtime_binding

HealthState = str
_RUNNING_APP_STATES = frozenset({"ACTIVE", "HEALTHY", "RUNNING", "STARTED", "UP"})
_DOWN_APP_STATES = frozenset({"CRASHED", "DEPLOYING", "DOWN", "ERROR", "FAILED", "STOPPED", "STOPPING"})
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
    binding: RuntimeBinding | None,
) -> ObservedApp | None:
    if runtime is None or not runtime.reachable:
        return None
    if binding is not None and binding.provider == "truenas-app":
        matches = [app for app in runtime.apps if match_runtime_binding(app, binding)[0]]
        return matches[0] if len(matches) == 1 else None
    candidates = {candidate for candidate in (_key(service.source_id), _key(service.service_id), _key(service.name)) if candidate}
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


def _runtime_binding_missing(
    binding: RuntimeBinding | None,
    runtime: TrueNASRuntimeSnapshot | None,
    app: ObservedApp | None,
) -> bool:
    """Return whether a declared TrueNAS app binding is absent from fresh runtime evidence."""
    return bool(
        binding is not None and binding.provider == "truenas-app" and runtime is not None and runtime.reachable and not runtime.stale and app is None,
    )


def _tunnel_state(status: str | None) -> HealthState | None:
    normalized = (status or "").strip().upper()
    if normalized in _HEALTHY_TUNNEL_STATES:
        return "ok"
    if normalized in _DOWN_TUNNEL_STATES:
        return "fail"
    return "warn" if normalized else None


def _tunnel_by_hostname(
    observations: Iterable[CloudflareTunnelObservation],
) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for tunnel in observations:
        for ingress in tunnel.ingress:
            result[ingress.hostname.lower().rstrip(".")] = {
                "tunnel_status": ingress.status or tunnel.status,
                "tunnel_name": ingress.tunnel_name or tunnel.name,
            }
    return result


def _from_direct(
    direct: HealthState | None,
    internal: HealthState | None,
    runtime: HealthState | None,
    tunnel: HealthState | None,
) -> HealthState | None:
    if direct == "ok":
        if tunnel == "fail":
            return "warn"
        return "warn" if internal == "fail" else "ok"
    if direct == "warn":
        if tunnel == "fail":
            return "warn" if "ok" in {internal, runtime} else "fail"
        return "warn"
    if direct == "fail":
        return "warn" if "ok" in {internal, runtime} else "fail"
    return None


def reconcile_service_state(
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
    """Apply evidence precedence without letting edge uncertainty invent downtime."""
    origin_proven_up = internal == "ok" or 200 <= direct_http_status < 300
    if runtime_missing:
        return "warn" if origin_proven_up else "fail"
    if application_error:
        return "warn"
    if runtime == "fail":
        return "warn" if origin_proven_up else "fail"

    direct_state = _from_direct(direct, internal, runtime, tunnel)
    if direct_state is not None:
        return direct_state
    if internal == "ok":
        return "ok"
    if internal == "fail":
        return "warn" if runtime == "ok" else "fail"
    if runtime == "ok":
        return "warn" if external else "ok"
    if tunnel is not None:
        return "warn"
    if any(state is not None for state in (internal, runtime, tunnel)):
        return "warn"
    return "unknown"


def _freshness(
    *,
    checked_at: str | None,
    direct_result: dict[str, Any] | None,
    internal_result: dict[str, Any] | None,
    runtime: TrueNASRuntimeSnapshot | None,
    app: ObservedApp | None,
    tunnel_evidence: dict[str, str | None] | None,
) -> tuple[str | None, int | None, bool]:
    if direct_result is not None or internal_result is not None or tunnel_evidence is not None:
        return checked_at, _observation_age_seconds(checked_at), False
    if runtime is not None and app is not None:
        return runtime.observed_at, _observation_age_seconds(runtime.observed_at), runtime.stale
    return None, None, False


def _enrich_service_row(
    row: dict[str, Any],
    *,
    service: HomelabService,
    runtime: TrueNASRuntimeSnapshot | None,
    cloudflare_stale: bool,
    cloudflare_status_confirmed: bool | None,
    cloudflare_warning: str | None,
    tunnel_evidence: dict[str, str | None] | None,
    direct_result: dict[str, Any] | None,
) -> None:
    """Attach optional notes/provider fields without inflating reconciliation complexity."""
    if service.health_note:
        row["health_note"] = service.health_note
    if runtime is not None:
        row["runtime_stale"] = runtime.stale
    if service.external and cloudflare_status_confirmed is False:
        row["cloudflare_status_confirmed"] = False
        row["cloudflare_warning"] = cloudflare_warning or "⚠️ Cloudflare global status could not be confirmed"
    if tunnel_evidence is not None:
        row["tunnel_stale"] = cloudflare_stale
        row.update(tunnel_evidence)
    if direct_result is not None:
        for key in ("latency_ms", "error", "application_error"):
            if key in direct_result:
                row[key] = direct_result[key]


def build_reconciled_service_health(
    services: list[HomelabService],
    *,
    public_results: list[dict[str, Any]],
    internal_results: list[dict[str, Any]],
    runtime: TrueNASRuntimeSnapshot | None,
    tunnels: Iterable[CloudflareTunnelObservation],
    runtime_bindings: Mapping[str, RuntimeBinding] | None = None,
    cloudflare_stale: bool = False,
    cloudflare_status_confirmed: bool | None = True,
    cloudflare_warning: str | None = None,
    checked_at: str | None = None,
) -> list[dict[str, Any]]:
    """Reconcile runtime, direct/LAN and edge evidence for each declared service."""
    direct_by_url = {normalized: result for result in public_results if (normalized := _normalized_url(str(result.get("url") or ""))) is not None}
    internal_by_id = {str(result.get("id")): result for result in internal_results if result.get("id")}
    tunnels_by_host = _tunnel_by_hostname(tunnels)
    rows: list[dict[str, Any]] = []
    for service in services:
        endpoint_url = service.effective_endpoint_url
        url = _normalized_url(endpoint_url)
        direct_result = direct_by_url.get(url) if url else None
        internal_result = internal_by_id.get(service.service_id)
        binding = (runtime_bindings or {}).get(service.service_id)
        app = _runtime_app_for_service(service, runtime, binding)
        runtime_health = None if runtime is not None and runtime.stale else _runtime_state(app)
        runtime_missing = _runtime_binding_missing(binding, runtime, app)
        tunnel_evidence = tunnels_by_host.get(_hostname(endpoint_url) or "")
        tunnel_status = str(tunnel_evidence.get("tunnel_status")) if tunnel_evidence and tunnel_evidence.get("tunnel_status") is not None else None
        tunnel_health = None if cloudflare_stale or cloudflare_status_confirmed is False else _tunnel_state(tunnel_status)
        direct_health = str(direct_result.get("state")) if direct_result else None
        internal_health = str(internal_result.get("state")) if internal_result else None
        application_error = bool(direct_result and direct_result.get("application_error"))
        state = reconcile_service_state(
            direct=direct_health,
            internal=internal_health,
            runtime=runtime_health,
            tunnel=tunnel_health,
            external=service.external,
            direct_http_status=int(direct_result.get("http_status", 0)) if direct_result else 0,
            application_error=application_error,
            runtime_missing=runtime_missing,
        )
        observed_at, age, stale = _freshness(
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
            "state": state,
            "tls_trusted": direct_result.get("tls_trusted") if direct_result else None,
            "direct_state": direct_health,
            "internal_state": internal_health,
            "runtime_state": app.state if app else None,
            "runtime_app": app.app_id if app else None,
            "runtime_reachable": runtime.reachable if runtime else None,
            "runtime_missing": runtime_missing,
            "observed_at": observed_at,
            "observation_age_seconds": age,
            "observation_stale": stale,
        }
        for prefix, result in (("direct", direct_result), ("internal", internal_result)):
            for source_key, target_key in (
                ("probe_source", f"{prefix}_probe_source"),
                ("probe_observed_at", f"{prefix}_probe_observed_at"),
                ("probe_age_seconds", f"{prefix}_probe_age_seconds"),
                ("probe_refresh_error", f"{prefix}_probe_refresh_error"),
            ):
                row[target_key] = result.get(source_key) if result else None
        _enrich_service_row(
            row,
            service=service,
            runtime=runtime,
            cloudflare_stale=cloudflare_stale,
            cloudflare_status_confirmed=cloudflare_status_confirmed,
            cloudflare_warning=cloudflare_warning,
            tunnel_evidence=tunnel_evidence,
            direct_result=direct_result,
        )
        rows.append(row)
    return rows
