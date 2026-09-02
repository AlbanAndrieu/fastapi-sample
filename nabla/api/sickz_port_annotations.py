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
        "expected_reachable": True,
        "access_policy": "trusted_sources_only",
        "default_action": "deny",
        "expected_from": ["fastapi_cloud", "approved_admin_sources"],
        "negative_probe_required": True,
        "reason": (
            "FastAPI Cloud requires the pfSense REST API on 10443 and currently has no "
            "user-controlled static egress/tunnel. Reachability is expected from this "
            "approved runtime, while unrelated Internet origins must remain denied."
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
        ports["10443"] = _port_10443_reachability(check)
        for port, metadata in _PORT_POLICY.items():
            existing = policy.get(port)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(metadata)
            policy[port] = merged
        break
    return payload
