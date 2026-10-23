"""Policy reconciliation for ``/sickz`` exposure checks.

The low-level sickz probe answers "did this URL respond?". This module answers the
security question the health board actually needs: "does what we observed match the
service's declared external, Cloudflare and runtime policy?"
"""

from __future__ import annotations

import asyncio
from collections import Counter
import re
from typing import Any
from urllib.parse import urlsplit


from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_access_applications,
    observe_cloudflare_tunnels,
)
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_runtime import ObservedApp, TrueNASRuntimeSnapshot, fetch_truenas_runtime
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence
from nabla.api.sickz_cloudflare_policy import (
    access_by_hostname as _access_by_hostname,
    access_policy_result as _access_policy_result,
    tunnel_policy_result as _tunnel_policy_result,
    tunnels_by_hostname as _tunnels_by_hostname,
)

_DIRECT_EXTERNAL_SUFFIX = ".int.albandrieu.com"
_DOWN_APP_STATES = frozenset({"CRASHED", "DOWN", "ERROR", "FAILED", "STOPPED"})
_GATEWAY_HTTP_STATUSES = frozenset({502, 503, 504})
_KEY_RE = re.compile(r"[^a-z0-9]+")
_SKULL_ICON_SRC = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/1f480.svg"


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


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _key(value: str | None) -> str:
    return _KEY_RE.sub("-", (value or "").strip().lower()).strip("-")


def _observed_http_status(check: dict[str, Any]) -> int | None:
    value = check.get("http_status")
    if isinstance(value, int):
        return value
    aliases = check.get("alias_results")
    if not isinstance(aliases, dict):
        return None
    for result in aliases.values():
        if isinstance(result, dict) and isinstance(result.get("http_status"), int):
            return int(result["http_status"])
    return None


async def _observe_cloudflare() -> tuple[
    list[CloudflareTunnelObservation],
    list[CloudflareAccessApplicationObservation],
    bool,
    str | None,
    str | None,
]:
    """Observe Tunnel and Access independently so missing Access scope stays explicit."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return [], [], False, None, None

    async def tunnels() -> tuple[list[CloudflareTunnelObservation], str | None]:
        try:
            return await asyncio.to_thread(observe_cloudflare_tunnels), None
        except Exception as exc:  # pragma: no cover - provider/network dependent
            return [], type(exc).__name__

    async def access() -> tuple[list[CloudflareAccessApplicationObservation], str | None]:
        try:
            return await asyncio.to_thread(observe_cloudflare_access_applications), None
        except Exception as exc:  # pragma: no cover - provider/network/permissions dependent
            return [], type(exc).__name__

    tunnel_result, access_result = await asyncio.gather(tunnels(), access())
    tunnel_observations, tunnel_error = tunnel_result
    access_observations, access_error = access_result
    return tunnel_observations, access_observations, True, tunnel_error, access_error


def _runtime_app_for_service(
    service: HomelabService,
    runtime: TrueNASRuntimeSnapshot,
) -> ObservedApp | None:
    if not runtime.reachable:
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
    matches = [app for app in runtime.apps if candidates.intersection({_key(app.app_id), _key(app.name)})]
    return matches[0] if len(matches) == 1 else None


def _runtime_evidence(
    service: HomelabService,
    runtime: TrueNASRuntimeSnapshot,
    http_status: int | None,
) -> dict[str, Any]:
    app = _runtime_app_for_service(service, runtime)
    if app is None:
        return {
            "truenas_runtime_reachable": runtime.reachable,
            "truenas_runtime_stale": runtime.stale,
        }

    state = app.state.strip().upper()
    failed = state in _DOWN_APP_STATES and runtime.reachable and not runtime.stale
    out: dict[str, Any] = {
        "runtime_app": app.app_id,
        "runtime_state": app.state,
        "runtime_failed": failed,
        "truenas_runtime_reachable": runtime.reachable,
        "truenas_runtime_stale": runtime.stale,
    }
    if failed:
        out["failure_icon"] = "skull"
        out["icon_src"] = _SKULL_ICON_SRC
        if http_status in _GATEWAY_HTTP_STATUSES:
            out["failure_detail"] = (
                f"💀 HTTP {http_status} Bad Gateway/upstream failure matches TrueNAS app state {app.state}; the public edge is alive but the service workload is not running."
            )
        else:
            out["failure_detail"] = f"💀 TrueNAS reports app state {app.state}; the service workload is not running."
    return out


def _secure_external_policy(
    *,
    reachable: bool,
    tls_trusted: bool | None,
    http_status: int | None,
    tunnel_evidence: dict[str, Any] | None,
    observer_configured: bool,
    tunnel_observer_error: str | None,
    access_observer_error: str | None,
    access_required: bool,
    access_evidence: dict[str, Any] | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str]:
    if not reachable:
        return "fail", "external=true expects the service to be reachable from the Internet."
    if tls_trusted is False:
        return "fail", "Service is reachable but its public TLS certificate is not trusted."
    if http_status is not None and http_status >= 500:
        return "fail", f"Service is externally reachable but returns HTTP {http_status}."

    tunnel_status, tunnel_detail = _tunnel_policy_result(
        tunnel_evidence=tunnel_evidence,
        observer_configured=observer_configured,
        tunnel_observer_error=tunnel_observer_error,
        http_evidence=http_evidence,
    )
    if tunnel_status == "fail":
        return "fail", tunnel_detail

    access_result = _access_policy_result(
        access_required=access_required,
        access_evidence=access_evidence,
        access_observer_error=access_observer_error,
        http_evidence=http_evidence,
    )
    if access_result is None:
        return tunnel_status, tunnel_detail or "Cloudflare Tunnel posture is compliant."

    access_status, access_detail = access_result
    detail = f"{tunnel_detail} {access_detail}".strip()
    if access_status == "fail":
        return "fail", detail
    if access_status == "warn" or tunnel_status == "warn":
        return "warn", detail
    return "ok", detail


def _direct_external_policy(
    *,
    host: str,
    reachable: bool,
    tls_trusted: bool | None,
    tunnel_evidence: dict[str, Any] | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str]:
    if tls_trusted is False:
        return (
            "fail",
            "Direct external exposure is configured, but the public TLS certificate is not trusted.",
        )
    if tunnel_evidence is not None:
        return (
            "fail",
            "tunnelSecure=false declares direct exposure, but a Cloudflare Tunnel ingress is also observed; configuration intent and reality conflict.",
        )

    bits = [
        "⚠️ Direct external exposure without Cloudflare is explicitly allowed by policy but remains a security debt.",
    ]
    if host.endswith(_DIRECT_EXTERNAL_SUFFIX):
        bits.append("*.int.albandrieu.com is the intentional direct-Traefik exception.")
    if reachable:
        bits.append("The endpoint is currently reachable as declared.")
    else:
        bits.append("The external probe could not currently reach the endpoint; keep the warning because the declared design is still direct exposure.")
    if tls_trusted is True:
        bits.append("Public TLS is trusted.")
    if http_evidence.get("cloudflare_http_evidence"):
        bits.append("Cloudflare edge headers were unexpectedly observed; verify DNS/proxy mode.")
    return "warn", " ".join(bits)


def _classify_service(
    service: HomelabService,
    check: dict[str, Any],
    *,
    tunnel_evidence: dict[str, Any] | None,
    observer_configured: bool,
    observer_error: str | None,
    http_evidence: dict[str, Any],
    access_evidence: dict[str, Any] | None = None,
    access_observer_error: str | None = None,
) -> tuple[str, str]:
    """Classify one service while keeping the existing test-call contract stable."""
    reachable = check.get("reachable") is True
    tls_value = check.get("tls_trusted")
    tls_trusted = tls_value if isinstance(tls_value, bool) else None
    http_status = _observed_http_status(check)
    host = _hostname(service.tunnel_url) or ""

    if not service.external:
        if tunnel_evidence is not None:
            return (
                "fail",
                "external=false but a Cloudflare Tunnel ingress exists for this hostname; exposure policy is violated.",
            )
        if access_evidence is not None:
            return (
                "fail",
                "external=false but a Cloudflare Access application exists for this hostname; public exposure configuration should be removed.",
            )
        if reachable:
            return (
                "fail",
                "external=false but the endpoint is reachable from FastAPI Cloud; it should not be exposed externally.",
            )
        return "ok", "external=false and the endpoint is not reachable from the external probe."

    if service.tunnel_secure is False:
        return _direct_external_policy(
            host=host,
            reachable=reachable,
            tls_trusted=tls_trusted,
            tunnel_evidence=tunnel_evidence,
            http_evidence=http_evidence,
        )

    if service.tunnel_secure is True:
        return _secure_external_policy(
            reachable=reachable,
            tls_trusted=tls_trusted,
            http_status=http_status,
            tunnel_evidence=tunnel_evidence,
            observer_configured=observer_configured,
            tunnel_observer_error=observer_error,
            access_observer_error=access_observer_error,
            access_required=service.effective_cloudflare_access_required,
            access_evidence=access_evidence,
            http_evidence=http_evidence,
        )

    return (
        "warn",
        "external=true but tunnelSecure is unspecified; the intended security boundary is ambiguous.",
    )


async def enrich_sickz_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconcile low-level sickz observations with catalog, Cloudflare and TrueNAS."""
    if payload.get("status") == "skipped_internal_network":
        return payload

    services_task = asyncio.create_task(fetch_homelab_services())
    cloudflare_task = asyncio.create_task(_observe_cloudflare())
    runtime_task = asyncio.create_task(fetch_truenas_runtime())
    services, cloudflare_result, runtime = await asyncio.gather(
        services_task,
        cloudflare_task,
        runtime_task,
    )
    (
        tunnel_observations,
        access_observations,
        observer_configured,
        tunnel_observer_error,
        access_observer_error,
    ) = cloudflare_result

    services_by_url = {normalized: service for service in services if (normalized := _normalized_url(service.tunnel_url)) is not None}
    tunnels_by_host = _tunnels_by_hostname(tunnel_observations)
    access_by_host = _access_by_hostname(access_observations)

    checks = {key: dict(value) if isinstance(value, dict) else value for key, value in payload.get("checks", {}).items()}
    matched: list[tuple[str, dict[str, Any], HomelabService]] = []
    for key, check in checks.items():
        if not isinstance(check, dict):
            continue
        url = _normalized_url(str(check.get("tunnel_url") or check.get("href") or ""))
        service = services_by_url.get(url or "")
        if service is not None:
            matched.append((key, check, service))

    evidence_results = await asyncio.gather(
        *(
            _probe_http_edge_evidence(
                service.tunnel_url or "",
                allow_service_token=bool(
                    service.external and (service.tunnel_secure is True or service.effective_cloudflare_access_required),
                ),
            )
            for _, _, service in matched
        ),
    )

    for (key, check, service), http_evidence in zip(
        matched,
        evidence_results,
        strict=True,
    ):
        host = _hostname(service.tunnel_url) or ""
        tunnel_evidence = tunnels_by_host.get(host)
        access_evidence = access_by_host.get(host)
        http_status = _observed_http_status(check)
        runtime_evidence = _runtime_evidence(service, runtime, http_status)
        policy_status, policy_detail = _classify_service(
            service,
            check,
            tunnel_evidence=tunnel_evidence,
            observer_configured=observer_configured,
            observer_error=tunnel_observer_error,
            http_evidence=http_evidence,
            access_evidence=access_evidence,
            access_observer_error=access_observer_error,
        )

        failure_detail = runtime_evidence.get("failure_detail")
        if failure_detail:
            policy_status = "fail"
            policy_detail = f"{policy_detail} {failure_detail}".strip()
        if service.security_exception:
            policy_detail = f"{policy_detail} Known policy exception: {service.security_exception}".strip()

        check.update(
            {
                "external": service.external,
                "tunnel_secure": service.tunnel_secure,
                "cloudflare_access_required": service.effective_cloudflare_access_required,
                "security_exception": service.security_exception,
                "policy_status": policy_status,
                "policy_detail": policy_detail,
                "cloudflare_observer_configured": observer_configured,
                **http_evidence,
                **runtime_evidence,
            },
        )
        if tunnel_evidence is not None:
            check.update(tunnel_evidence)
        if access_evidence is not None:
            check.update(access_evidence)
        checks[key] = check

    counts = Counter(str(check.get("policy_status")) for check in checks.values() if isinstance(check, dict) and check.get("policy_status"))
    return {
        **payload,
        "checks": checks,
        "policy_version": 2,
        "policy_counts": dict(counts),
        "cloudflare_observer_configured": observer_configured,
        "cloudflare_tunnels_observed": len(tunnel_observations),
        "cloudflare_access_apps_observed": len(access_observations),
        "cloudflare_observer_error": tunnel_observer_error,
        "cloudflare_access_observer_error": access_observer_error,
        "truenas_runtime_reachable": runtime.reachable,
        "truenas_runtime_stale": runtime.stale,
    }
