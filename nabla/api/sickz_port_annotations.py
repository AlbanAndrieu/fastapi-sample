"""Post-process pfSense port observations with stable service/security metadata."""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse


_PORT_POLICY: dict[str, dict[str, Any]] = {
    "22": {
        "service": "SSH",
        "expected_reachable": False,
        "reason": "Remote shell access must not be exposed to FastAPI Cloud.",
    },
    "3000": {
        "service": "ntopng",
        "expected_reachable": False,
        "reason": "ntopng administration must not be exposed directly to FastAPI Cloud.",
    },
    "4000": {
        "service": "LiteLLM",
        "expected_reachable": False,
        "reason": "LiteLLM must only be exposed through its approved proxy/tunnel path.",
    },
    "8200": {
        "service": "Vault",
        "expected_reachable": False,
        "reason": "Vault API must not be exposed directly to FastAPI Cloud.",
    },
    "10443": {
        "service": "pfSense Admin/API",
        "expected_reachable": False,
        "direct_probe_semantics": "negative_exposure_check",
        "recommended_control_path": "out_of_band",
        "access_policy": "trusted_sources_only",
        "default_action": "deny",
        "expected_from": ["approved_admin_sources"],
        "negative_probe_required": True,
        "reason": (
            "FastAPI Cloud is not an approved administration source for pfSense WAN 10443. "
            "A successful direct probe is a security-policy failure; durable posture and "
            "Snort telemetry should use an out-of-band observer."
        ),
    },
}


def _is_pfsense_check(check: Any) -> bool:
    if not isinstance(check, dict):
        return False
    if isinstance(check.get("pfsense_tcp_ports"), dict):
        return True
    return str(check.get("name") or check.get("display_label") or "").casefold() == "pfsense"


def _is_private_alias(raw: Any) -> bool:
    try:
        host = urlparse(str(raw)).hostname or ""
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _alias_10443_reachability(
    check: dict[str, Any],
    *,
    private_only: bool = False,
) -> bool | None:
    alias_results = check.get("alias_results")
    aliases = check.get("aliases_probed")
    if not isinstance(alias_results, dict) or not isinstance(aliases, list):
        return None

    observations: list[bool] = []
    for raw in aliases:
        try:
            parsed = urlparse(str(raw))
        except ValueError:
            continue
        if parsed.port != 10443 or (private_only and not _is_private_alias(raw)):
            continue
        result = alias_results.get(raw)
        if isinstance(result, dict) and isinstance(result.get("reachable"), bool):
            observations.append(result["reachable"])
    if any(observations):
        return True
    if observations:
        return False
    return None


def _port_10443_reachability(check: dict[str, Any]) -> bool | None:
    """Derive 10443 from the actual pfSense HTTPS alias probes, not raw TCP."""
    observed = _alias_10443_reachability(check)
    if observed is not None:
        return observed
    reachable = check.get("reachable")
    return reachable if isinstance(reachable, bool) else None


def _apply_source_aware_10443_policy(
    check: dict[str, Any],
    reachable: bool | None,
    *,
    runtime_scope: str,
) -> None:
    """Apply pfSense 10443 policy according to the observer's network trust scope."""
    trusted_lan_runtime = runtime_scope in {"local", "homelab"}
    private_reachable = _alias_10443_reachability(check, private_only=True)

    if trusted_lan_runtime:
        if private_reachable is True:
            status = "ok"
            detail = (
                "✅ pfSense REST/API 10443 is reachable through its private LAN address "
                f"from the trusted {runtime_scope} observer. This is expected for local "
                "administration and does not prove WAN exposure."
            )
        elif reachable is True:
            status = "warn"
            detail = (
                "⚠️ pfSense REST/API 10443 is reachable from the trusted local observer, "
                "but no private 10443 alias probe succeeded. Treat this as ambiguous "
                "routing evidence and keep the independent external negative exposure "
                "probe as the WAN security control."
            )
        elif private_reachable is False:
            status = "warn"
            detail = (
                "⚠️ pfSense REST/API 10443 is not reachable through its private LAN "
                f"address from the {runtime_scope} observer. This is a local control-path "
                "availability issue, not evidence of safe WAN blocking."
            )
        else:
            status = "unknown"
            detail = (
                "pfSense REST/API 10443 private-LAN reachability is unknown from this "
                f"{runtime_scope} observer."
            )
    elif reachable is True:
        status = "fail"
        source = "FastAPI Cloud" if runtime_scope == "fastapi_cloud" else "cloud/PaaS"
        detail = (
            f"🚨 pfSense REST/API 10443 is reachable from {source}, but this runtime "
            "is not an approved administration source. This violates the intended WAN "
            "default-deny policy; inspect broad WAN pass rules before relying on sshguard "
            "or another dynamic blocklist to hide the exposure."
        )
    elif reachable is False:
        status = "ok"
        source = "FastAPI Cloud" if runtime_scope == "fastapi_cloud" else "cloud/PaaS"
        detail = (
            f"✅ pfSense REST/API 10443 is blocked from {source} as intended. "
            "Keep administration limited to approved stable sources and use the "
            "out-of-band observer for durable posture/Snort telemetry."
        )
    else:
        status = "unknown"
        source = "FastAPI Cloud" if runtime_scope == "fastapi_cloud" else "cloud/PaaS"
        detail = (
            f"pfSense REST/API 10443 reachability from {source} is unknown. "
            "The expected state is blocked; use the out-of-band observer for durable "
            "control-plane telemetry."
        )

    exception = str(check.get("security_exception") or "").strip()
    if exception:
        detail = f"{detail} Known policy exception: {exception}"
    check["policy_status"] = status
    check["policy_detail"] = detail


def enrich_pfsense_port_annotations(
    payload: dict[str, Any],
    *,
    runtime_scope: str = "fastapi_cloud",
) -> dict[str, Any]:
    """Add stable service names and the source-aware pfSense 10443 policy."""
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return payload

    for check in checks.values():
        if not _is_pfsense_check(check):
            continue
        ports = check.setdefault("pfsense_tcp_ports", {})
        policy = check.setdefault("pfsense_tcp_port_policy", {})
        if not isinstance(ports, dict) or not isinstance(policy, dict):
            continue
        reachability_10443 = _port_10443_reachability(check)
        ports["10443"] = reachability_10443
        for port, metadata in _PORT_POLICY.items():
            existing = policy.get(port)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(metadata)
            if port == "10443" and runtime_scope in {"local", "homelab"}:
                merged.update(
                    {
                        "expected_reachable": True,
                        "direct_probe_semantics": "trusted_lan_control_check",
                        "recommended_control_path": "direct_lan",
                        "expected_from": ["trusted_lan", "approved_admin_sources"],
                        "negative_probe_required": False,
                        "reason": (
                            "Trusted local/homelab observers may reach pfSense 10443 through "
                            "the private LAN path; WAN exposure must be evaluated by an "
                            "independent external negative probe."
                        ),
                    }
                )
            merged["observer_scope"] = runtime_scope
            policy[port] = merged
        _apply_source_aware_10443_policy(
            check,
            reachability_10443,
            runtime_scope=runtime_scope,
        )
        break
    return payload
