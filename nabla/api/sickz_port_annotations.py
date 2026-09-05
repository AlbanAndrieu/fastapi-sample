"""Post-process pfSense port observations with stable service/security metadata."""

from __future__ import annotations

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


def _port_10443_reachability(check: dict[str, Any]) -> bool | None:
    """Derive 10443 from the actual pfSense HTTPS alias probes, not raw TCP."""
    alias_results = check.get("alias_results")
    aliases = check.get("aliases_probed")
    if isinstance(alias_results, dict) and isinstance(aliases, list):
        observations: list[bool] = []
        for raw in aliases:
            try:
                parsed = urlparse(str(raw))
            except ValueError:
                continue
            if parsed.port != 10443:
                continue
            result = alias_results.get(raw)
            if isinstance(result, dict) and isinstance(result.get("reachable"), bool):
                observations.append(result["reachable"])
        if any(observations):
            return True
        if observations:
            return False
    reachable = check.get("reachable")
    return reachable if isinstance(reachable, bool) else None


def _apply_source_aware_10443_policy(
    check: dict[str, Any],
    reachable: bool | None,
) -> None:
    """Override the legacy external=false verdict with the current trusted-source contract."""
    if reachable is True:
        status = "fail"
        detail = (
            "🚨 pfSense REST/API 10443 is reachable from FastAPI Cloud, but this runtime "
            "is not an approved administration source. This violates the intended WAN "
            "default-deny policy; inspect broad WAN pass rules before relying on sshguard "
            "or another dynamic blocklist to hide the exposure."
        )
    elif reachable is False:
        status = "ok"
        detail = (
            "✅ pfSense REST/API 10443 is blocked from FastAPI Cloud as intended. "
            "Keep administration limited to approved stable sources and use the "
            "out-of-band observer for durable posture/Snort telemetry."
        )
    else:
        status = "unknown"
        detail = (
            "pfSense REST/API 10443 reachability from FastAPI Cloud is unknown. "
            "The expected state is blocked; use the out-of-band observer for durable "
            "control-plane telemetry."
        )

    exception = str(check.get("security_exception") or "").strip()
    if exception:
        detail = f"{detail} Known policy exception: {exception}"
    check["policy_status"] = status
    check["policy_detail"] = detail


def enrich_pfsense_port_annotations(payload: dict[str, Any]) -> dict[str, Any]:
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
            policy[port] = merged
        _apply_source_aware_10443_policy(check, reachability_10443)
        break
    return payload
