"""Policy reconciliation for ``/sickz`` exposure checks.

The low-level sickz probe answers "did this URL respond?".  This module answers the
security question the health board actually needs: "does what we observed match the
service's declared external/Cloudflare exposure policy?"
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

from nabla.api.cloudflare_tunnels import (
    CloudflareTunnelObservation,
    CloudflareTunnelSettings,
    observe_cloudflare_tunnels,
)
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService

_DIRECT_EXTERNAL_SUFFIX = ".int.albandrieu.com"
_DOWN_TUNNEL_STATES = frozenset({"DOWN", "FAILED", "INACTIVE"})


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


def _tunnels_by_hostname(
    observations: Iterable[CloudflareTunnelObservation],
) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    for tunnel in observations:
        for ingress in tunnel.ingress:
            out[ingress.hostname.lower().rstrip(".")] = {
                "cloudflare_tunnel_observed": True,
                "cloudflare_tunnel_name": ingress.tunnel_name or tunnel.name,
                "cloudflare_tunnel_status": ingress.status or tunnel.status,
                "cloudflare_origin_service": ingress.service,
            }
    return out


async def _observe_cloudflare() -> tuple[list[CloudflareTunnelObservation], bool, str | None]:
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return [], False, None
    try:
        observations = await asyncio.to_thread(observe_cloudflare_tunnels)
    except Exception as exc:  # pragma: no cover - provider/network dependent
        return [], True, type(exc).__name__
    return observations, True, None


async def _probe_http_edge_evidence(url: str) -> dict[str, Any]:
    """Collect sanitized HTTP edge evidence without hiding invalid certificates."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=False,  # noqa: S501 - TLS trust is checked separately by sickz
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "nabla-sickz-policy-probe/1.0"},
            )
    except (httpx.HTTPError, OSError):
        return {
            "cloudflare_http_evidence": False,
            "cloudflare_access_signal": False,
        }

    server = response.headers.get("server", "").casefold()
    location = response.headers.get("location", "").casefold()
    cf_mitigated = response.headers.get("cf-mitigated", "").casefold()
    cloudflare_edge = bool(
        response.headers.get("cf-ray")
        or response.headers.get("cf-cache-status")
        or "cloudflare" in server
        or cf_mitigated
    )
    access_signal = bool(
        "cloudflareaccess.com" in location
        or cf_mitigated in {"challenge", "managed_challenge"}
    )
    return {
        "cloudflare_http_evidence": cloudflare_edge,
        "cloudflare_access_signal": access_signal,
        "http_evidence_status": response.status_code,
    }


def _secure_external_policy(
    *,
    reachable: bool,
    tls_trusted: bool | None,
    http_status: int | None,
    tunnel_evidence: dict[str, Any] | None,
    observer_configured: bool,
    observer_error: str | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str]:
    if not reachable:
        return "fail", "external=true expects the service to be reachable from the Internet."
    if tls_trusted is False:
        return "fail", "Service is reachable but its public TLS certificate is not trusted."
    if http_status is not None and http_status >= 500:
        return "fail", f"Service is externally reachable but returns HTTP {http_status}."

    if tunnel_evidence is not None:
        status = str(tunnel_evidence.get("cloudflare_tunnel_status") or "").upper()
        if status in _DOWN_TUNNEL_STATES:
            return "fail", f"Cloudflare Tunnel ingress exists but reports status {status}."
        return "ok", "Reachable with trusted TLS and an observed Cloudflare Tunnel ingress."

    edge_seen = bool(http_evidence.get("cloudflare_http_evidence"))
    if observer_error:
        if edge_seen:
            return (
                "warn",
                "Cloudflare HTTP edge evidence is present, but the read-only Tunnel observer failed; tunnel routing could not be verified.",
            )
        return (
            "warn",
            "The Cloudflare observer failed and HTTP did not provide Cloudflare edge evidence; protection is unverified.",
        )
    if not observer_configured:
        if edge_seen:
            return (
                "warn",
                "Cloudflare HTTP edge evidence is present, but the read-only Tunnel observer is not configured.",
            )
        return (
            "fail",
            "tunnelSecure=true but neither a Cloudflare Tunnel ingress nor Cloudflare HTTP edge evidence was observed.",
        )
    if edge_seen:
        return (
            "warn",
            "Cloudflare edge headers were observed, but this hostname is absent from the read-only Tunnel ingress inventory.",
        )
    return (
        "fail",
        "tunnelSecure=true but the hostname is reachable without any observed Cloudflare Tunnel/edge evidence.",
    )


def _direct_external_policy(
    *,
    host: str,
    reachable: bool,
    tls_trusted: bool | None,
    tunnel_evidence: dict[str, Any] | None,
) -> tuple[str, str]:
    bits = [
        "⚠️ Direct external exposure without Cloudflare is explicitly allowed by policy but remains a security debt."
    ]
    if host.endswith(_DIRECT_EXTERNAL_SUFFIX):
        bits.append("*.int.albandrieu.com is the intentional direct-Traefik exception.")
    if reachable:
        bits.append("The endpoint is currently reachable as declared.")
    else:
        bits.append("The external probe could not currently reach the endpoint.")
    if tls_trusted is True:
        bits.append("Public TLS is trusted.")
    elif tls_trusted is False:
        bits.append("Public TLS is NOT trusted and should be corrected.")
    if tunnel_evidence is not None:
        bits.append("A Cloudflare Tunnel ingress was also observed, which conflicts with tunnelSecure=false.")
    return "warn", " ".join(bits)


def _classify_service(
    service: HomelabService,
    check: dict[str, Any],
    *,
    tunnel_evidence: dict[str, Any] | None,
    observer_configured: bool,
    observer_error: str | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str]:
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
        )

    if service.tunnel_secure is True:
        return _secure_external_policy(
            reachable=reachable,
            tls_trusted=tls_trusted,
            http_status=http_status,
            tunnel_evidence=tunnel_evidence,
            observer_configured=observer_configured,
            observer_error=observer_error,
            http_evidence=http_evidence,
        )

    return (
        "warn",
        "external=true but tunnelSecure is unspecified; the intended security boundary is ambiguous.",
    )


async def enrich_sickz_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconcile low-level sickz observations with catalog and Cloudflare intent."""
    if payload.get("status") == "skipped_internal_network":
        return payload

    services_task = asyncio.create_task(fetch_homelab_services())
    cloudflare_task = asyncio.create_task(_observe_cloudflare())
    services, cloudflare_result = await asyncio.gather(services_task, cloudflare_task)
    observations, observer_configured, observer_error = cloudflare_result

    services_by_url = {
        normalized: service
        for service in services
        if (normalized := _normalized_url(service.tunnel_url)) is not None
    }
    tunnels_by_host = _tunnels_by_hostname(observations)

    checks = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in payload.get("checks", {}).items()
    }
    matched: list[tuple[str, dict[str, Any], HomelabService]] = []
    for key, check in checks.items():
        if not isinstance(check, dict):
            continue
        url = _normalized_url(str(check.get("tunnel_url") or check.get("href") or ""))
        service = services_by_url.get(url or "")
        if service is not None:
            matched.append((key, check, service))

    evidence_results = await asyncio.gather(
        *(_probe_http_edge_evidence(service.tunnel_url or "") for _, _, service in matched)
    )

    for (key, check, service), http_evidence in zip(
        matched,
        evidence_results,
        strict=True,
    ):
        host = _hostname(service.tunnel_url) or ""
        tunnel_evidence = tunnels_by_host.get(host)
        policy_status, policy_detail = _classify_service(
            service,
            check,
            tunnel_evidence=tunnel_evidence,
            observer_configured=observer_configured,
            observer_error=observer_error,
            http_evidence=http_evidence,
        )
        check.update(
            {
                "external": service.external,
                "tunnel_secure": service.tunnel_secure,
                "policy_status": policy_status,
                "policy_detail": policy_detail,
                "cloudflare_observer_configured": observer_configured,
                **http_evidence,
            }
        )
        if tunnel_evidence is not None:
            check.update(tunnel_evidence)
        checks[key] = check

    counts = Counter(
        str(check.get("policy_status"))
        for check in checks.values()
        if isinstance(check, dict) and check.get("policy_status")
    )
    return {
        **payload,
        "checks": checks,
        "policy_version": 1,
        "policy_counts": dict(counts),
        "cloudflare_observer_configured": observer_configured,
        "cloudflare_tunnels_observed": len(observations),
        "cloudflare_observer_error": observer_error,
    }
