"""Reconcile direct, TrueNAS runtime and Cloudflare ingress health evidence."""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from nabla.api.cloudflare_tunnels import CloudflareTunnelObservation
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot

HealthState = str

_RUNNING_APP_STATES = frozenset({"ACTIVE", "HEALTHY", "RUNNING", "STARTED", "UP"})
_DOWN_APP_STATES = frozenset({"CRASHED", "DOWN", "ERROR", "FAILED", "STOPPED"})
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


def _runtime_app_for_service(
    service: HomelabService,
    runtime: TrueNASRuntimeSnapshot | None,
) -> ObservedApp | None:
    if runtime is None or not runtime.reachable:
        return None

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

    matches = [
        app
        for app in runtime.apps
        if candidates.intersection({_key(app.app_id), _key(app.name)})
    ]
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


def _reconciled_state(
    *,
    direct: HealthState | None,
    internal: HealthState | None,
    runtime: HealthState | None,
    tunnel: HealthState | None,
    external: bool,
) -> HealthState:
    """Prefer measured reachability while avoiding false-red cloud/private probes."""
    if direct == "ok":
        return "warn" if runtime == "fail" or tunnel == "fail" else "ok"
    if direct == "warn":
        return "warn"
    if direct == "fail":
        if "ok" in {internal, runtime, tunnel}:
            return "warn"
        return "fail"

    # Private services are not HTTP-probed from FastAPI Cloud. A successful LAN
    # TCP probe is sufficient for green; TrueNAS/runtime-only evidence is orange
    # because it proves the workload is up but not that the UI endpoint is usable.
    if internal == "ok":
        return "ok"
    if runtime == "ok" or tunnel == "ok":
        return "warn"
    if runtime == "fail":
        return "fail"
    if external and tunnel == "fail":
        return "fail"

    # A failed LAN probe from a cloud runtime is not authoritative by itself.
    # Unknown/unverified endpoints therefore stay degraded rather than falsely red.
    return "warn"


def build_reconciled_service_health(
    services: list[HomelabService],
    *,
    public_results: list[dict[str, Any]],
    internal_results: list[dict[str, Any]],
    runtime: TrueNASRuntimeSnapshot | None,
    tunnels: Iterable[CloudflareTunnelObservation],
) -> list[dict[str, Any]]:
    """Return one URL health row per catalog service with multi-source evidence."""
    direct_by_url = {
        normalized: result
        for result in public_results
        if (normalized := _normalized_url(str(result.get("url") or ""))) is not None
    }
    internal_by_id = {
        str(result.get("id")): result
        for result in internal_results
        if result.get("id")
    }
    tunnels_by_host = _tunnel_by_hostname(tunnels)

    rows: list[dict[str, Any]] = []
    for service in services:
        url = _normalized_url(service.tunnel_url)
        if url is None:
            continue

        direct_result = direct_by_url.get(url)
        internal_result = internal_by_id.get(service.service_id)
        app = _runtime_app_for_service(service, runtime)
        runtime_health = _runtime_state(app)
        host = _hostname(url)
        tunnel_evidence = tunnels_by_host.get(host or "")
        tunnel_status = (
            str(tunnel_evidence.get("tunnel_status"))
            if tunnel_evidence and tunnel_evidence.get("tunnel_status") is not None
            else None
        )
        tunnel_health = _tunnel_state(tunnel_status)
        direct_health = (
            str(direct_result.get("state")) if direct_result is not None else None
        )
        internal_health = (
            str(internal_result.get("state")) if internal_result is not None else None
        )

        row: dict[str, Any] = {
            "id": service.service_id,
            "name": service.name,
            "url": url,
            "reachable": bool(direct_result and direct_result.get("reachable")),
            "http_status": int(direct_result.get("http_status", 0)) if direct_result else 0,
            "state": _reconciled_state(
                direct=direct_health,
                internal=internal_health,
                runtime=runtime_health,
                tunnel=tunnel_health,
                external=service.external,
            ),
            "tls_trusted": direct_result.get("tls_trusted") if direct_result else None,
            "direct_state": direct_health,
            "internal_state": internal_health,
            "runtime_state": app.state if app is not None else None,
            "runtime_app": app.app_id if app is not None else None,
            "runtime_reachable": runtime.reachable if runtime is not None else None,
        }

        if direct_result is not None:
            for key in ("latency_ms", "error"):
                if key in direct_result:
                    row[key] = direct_result[key]
        if tunnel_evidence is not None:
            row.update(tunnel_evidence)

        rows.append(row)

    return rows
