"""Cloudflare Tunnel and Access policy evaluation for ``/sickz`` reconciliation.

Pure functions: they index read-only Cloudflare observations by hostname and
classify the observed edge evidence against a service's declared protection.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nabla.api.cloudflare_tunnels import (
    CloudflareAccessApplicationObservation,
    CloudflareTunnelObservation,
)

DOWN_TUNNEL_STATES = frozenset({"DOWN", "FAILED", "INACTIVE"})


def tunnels_by_hostname(
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


def access_by_hostname(
    observations: Iterable[CloudflareAccessApplicationObservation],
) -> dict[str, dict[str, Any]]:
    """Aggregate Access apps and flag broad versus path-scoped public exceptions."""
    grouped: dict[str, list[CloudflareAccessApplicationObservation]] = {}
    for application in observations:
        grouped.setdefault(application.hostname, []).append(application)

    out: dict[str, dict[str, Any]] = {}
    for hostname, applications in grouped.items():
        public_host_policies: list[str] = []
        public_path_policies: list[str] = []
        decisions: list[str] = []
        domains: list[str] = []
        policy_labels: list[str] = []
        policy_count = 0
        for application in applications:
            domains.append(application.domain)
            root_scope = application.path in {"", "/", "/*", "*"}
            for policy in application.policies:
                policy_count += 1
                label = policy.name or policy.policy_id
                policy_labels.append(label)
                decision = (policy.decision or "").lower()
                if decision:
                    decisions.append(decision)
                public = decision == "bypass" or (decision == "allow" and policy.includes_everyone)
                if not public:
                    continue
                if root_scope:
                    public_host_policies.append(label)
                else:
                    public_path_policies.append(f"{application.path}: {label}")

        out[hostname] = {
            "cloudflare_access_observed": True,
            "cloudflare_access_domains": sorted(set(domains)),
            "cloudflare_access_application_count": len(applications),
            "cloudflare_access_policy_count": policy_count,
            "cloudflare_access_policy_names": sorted(set(policy_labels)),
            "cloudflare_access_policy_decisions": sorted(set(decisions)),
            "cloudflare_access_public": bool(public_host_policies or public_path_policies),
            "cloudflare_access_public_scope": ("host" if public_host_policies else "path" if public_path_policies else None),
            "cloudflare_access_public_policies": public_host_policies + public_path_policies,
        }
    return out


def _observed_access_policy_exception(
    *,
    access_evidence: dict[str, Any],
    default_deny: bool,
    service_auth_passed: bool,
) -> tuple[str, str] | None:
    """Return explicit Access-policy drift/public-scope findings when present."""
    raw_policy_count = access_evidence.get("cloudflare_access_policy_count")
    policy_count = raw_policy_count if isinstance(raw_policy_count, int) else None
    if policy_count == 0:
        if service_auth_passed:
            return (
                "warn",
                "Cloudflare Service Auth passed the live edge check, but the "
                "read-only Access observer reports an application with zero "
                "policies. Reconcile Cloudflare control-plane drift.",
            )
        detail = (
            "⚠️ Cloudflare Default-Deny blocked the anonymous request and the observed Access application contains no policy."
            if default_deny
            else "Cloudflare Access application is observed but contains no policy."
        )
        return "fail", detail + " Add the intended Cloudflare Access policy."

    public_scope = access_evidence.get("cloudflare_access_public_scope")
    if public_scope == "host":
        policies = ", ".join(access_evidence.get("cloudflare_access_public_policies") or [])
        return (
            "fail",
            "⚠️ Cloudflare Access permits or bypasses anonymous access for the whole hostname"
            + (f" ({policies})." if policies else ".")
            + " Check the Cloudflare Access policy; scope any webhook exception to a narrow path or use Service Auth.",
        )
    if public_scope == "path":
        policies = ", ".join(access_evidence.get("cloudflare_access_public_policies") or [])
        return (
            "warn",
            "⚠️ Cloudflare Access contains a path-scoped public bypass"
            + (f" ({policies})." if policies else ".")
            + " Keep the exception minimal and prefer Service Auth when the caller supports it.",
        )
    return None


def service_auth_access_result(
    *,
    blocked: bool,
    attempted: bool,
    passed: bool,
    observed_policy: bool,
) -> tuple[str, str] | None:
    """Classify the authenticated fallback independently from policy inventory."""
    if not blocked:
        return None
    if passed:
        detail = (
            "Cloudflare blocks the anonymous probe and the configured Service Token passes Access; the automated identity path is working."
            if observed_policy
            else "Cloudflare blocks anonymous access and the configured Service Token passes the live Access check."
        )
        return "ok", detail
    if attempted:
        detail = (
            "Cloudflare blocks the anonymous probe and the configured Service Token did not pass Access. Verify the Service Auth policy and token selectors."
            if observed_policy
            else "Cloudflare Access blocks the anonymous request and the configured Service Token did not pass."
        )
        return "fail", detail
    return None


def access_policy_result(
    *,
    access_required: bool,
    access_evidence: dict[str, Any] | None,
    access_observer_error: str | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str] | None:
    if not access_required:
        return None

    default_deny = http_evidence.get("cloudflare_default_deny") is True
    access_signal = http_evidence.get("cloudflare_access_signal") is True
    blocked = default_deny or access_signal
    service_auth_attempted = http_evidence.get("cloudflare_service_auth_attempted") is True
    service_auth_passed = http_evidence.get("cloudflare_service_token_access_passed") is True

    if access_evidence is not None:
        policy_exception = _observed_access_policy_exception(
            access_evidence=access_evidence,
            default_deny=default_deny,
            service_auth_passed=service_auth_passed,
        )
        if policy_exception is not None:
            return policy_exception

        service_auth_result = service_auth_access_result(
            blocked=blocked,
            attempted=service_auth_attempted,
            passed=service_auth_passed,
            observed_policy=True,
        )
        if service_auth_result is not None:
            return service_auth_result
        if default_deny:
            raw_policy_count = access_evidence.get("cloudflare_access_policy_count")
            policy_count = raw_policy_count if isinstance(raw_policy_count, int) else None
            return (
                "warn",
                "⚠️ Cloudflare Default-Deny blocked the anonymous probe even though "
                f"{policy_count if policy_count is not None else 'one or more'} Access policy/policies are observed. "
                "Verify policy selectors, precedence and the intended identity flow.",
            )
        return "ok", "Cloudflare Access application/policies are observed without a public Everyone/bypass exception."

    service_auth_result = service_auth_access_result(
        blocked=blocked,
        attempted=service_auth_attempted,
        passed=service_auth_passed,
        observed_policy=False,
    )
    if service_auth_result is not None:
        return service_auth_result
    if default_deny:
        return (
            "fail",
            "⚠️ Cloudflare Default-Deny blocked the hostname, but no matching Access application/policy was observed. An Access policy is probably missing.",
        )
    if access_signal:
        return "ok", "Cloudflare Access enforcement is visible in the anonymous HTTP response."
    if access_observer_error:
        return (
            "warn",
            f"Cloudflare Access policy could not be inspected ({access_observer_error}); protection is unverified even though the tunnel may be healthy.",
        )
    return (
        "fail",
        "Cloudflare Access protection is required but no Access application/policy or HTTP Access challenge was observed.",
    )


def tunnel_policy_result(
    *,
    tunnel_evidence: dict[str, Any] | None,
    observer_configured: bool,
    tunnel_observer_error: str | None,
    http_evidence: dict[str, Any],
) -> tuple[str, str]:
    if tunnel_evidence is not None:
        status = str(tunnel_evidence.get("cloudflare_tunnel_status") or "").upper()
        if status in DOWN_TUNNEL_STATES:
            return "fail", f"Cloudflare Tunnel ingress exists but reports status {status}."
        return "ok", "Cloudflare Tunnel ingress is observed."

    edge_seen = bool(http_evidence.get("cloudflare_http_evidence"))
    if tunnel_observer_error:
        detail = (
            "Cloudflare HTTP edge evidence is present but the Tunnel observer failed."
            if edge_seen
            else "The Cloudflare Tunnel observer failed and tunnel protection is unverified."
        )
        return "warn", detail
    if not observer_configured:
        detail = (
            "Cloudflare HTTP edge evidence is present but the read-only observer is not configured."
            if edge_seen
            else "tunnelSecure=true but no Cloudflare Tunnel/edge evidence was observed."
        )
        return ("warn" if edge_seen else "fail"), detail
    if edge_seen:
        return (
            "warn",
            "Cloudflare edge headers are present, but the hostname is absent from Tunnel ingress inventory.",
        )
    return (
        "fail",
        "tunnelSecure=true but the hostname has no observed Cloudflare Tunnel/edge evidence.",
    )
