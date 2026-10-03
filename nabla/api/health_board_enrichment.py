"""Pure health-board enrichments kept separate from snapshot orchestration."""

from __future__ import annotations

from typing import Any


def annotate_talos_vm_health(
    healthz: dict[str, Any],
    homelab: dict[str, Any],
) -> dict[str, Any]:
    """Expose Talos VM runtime evidence obtained through the TrueNAS observer."""
    truenas = homelab.get("truenas")
    api = truenas.get("api") if isinstance(truenas, dict) else None
    talos = api.get("talos") if isinstance(api, dict) else None
    if not isinstance(talos, dict):
        return healthz

    checks = dict(healthz.get("checks") or {})
    checks["talos"] = {
        **talos,
        "id": "talos",
        "service_id": "talos",
        "display_label": "Talos Linux · VM runtime",
    }
    return {**healthz, "checks": checks}


def annotate_pfsense_ingress_policy(
    healthz: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Make FastAPI Cloud connect-timeout evidence actionable without over-attribution."""
    if runtime.get("runtime_mode") != "fastapi_cloud":
        return healthz

    checks = dict(healthz.get("checks") or {})
    raw = checks.get("pfsense")
    if not isinstance(raw, dict):
        return healthz
    pfsense = dict(raw)
    if pfsense.get("reachable") is False and pfsense.get("error_kind") == "connect_timeout" and pfsense.get("failure_stage") == "connect":
        active_egress = [str(value) for value in runtime.get("active_egress_ips") or [] if isinstance(value, str) and value]
        pfsense["ingress_policy"] = {
            "state": "possible_ingress_policy_block",
            "access_policy": "trusted_sources_only",
            "active_egress_ips": active_egress,
            "possible_causes": [
                "trusted_source_policy_drift",
                "pf_or_snort_filter",
            ],
            "attribution_available": False,
            "detail": (
                "TCP/TLS connection did not complete before the 2s connect budget. "
                "The direct control path crosses the same pfSense WAN PF/Snort policy it "
                "tries to observe, so either trusted-source drift or a PF/Snort block can "
                "produce this timeout. This is pre-HTTP evidence, not an API credential "
                "failure."
            ),
            "recommended_control_path": "out_of_band",
        }
        checks["pfsense"] = pfsense
        return {**healthz, "checks": checks}
    return healthz


def annotate_truenas_ingress_policy(
    homelab: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Explain FastAPI Cloud TrueNAS pre-HTTP failures without claiming attribution."""
    if runtime.get("runtime_mode") != "fastapi_cloud":
        return homelab

    raw = homelab.get("truenas")
    if not isinstance(raw, dict):
        return homelab
    truenas = dict(raw)
    public = truenas.get("public")
    if not isinstance(public, dict):
        return homelab

    error_kind = str(public.get("error_kind") or "").strip().lower()
    failure_stage = str(public.get("failure_stage") or "").strip().lower()
    if error_kind not in {"connect_timeout", "connect_error"}:
        return homelab
    if failure_stage and failure_stage not in {"connect", "tcp_connect"}:
        return homelab

    active_egress = [
        str(value)
        for value in runtime.get("active_egress_ips") or []
        if isinstance(value, str) and value
    ]
    truenas["ingress_policy"] = {
        "state": "possible_ingress_policy_block",
        "access_policy": "trusted_sources_only",
        "active_egress_ips": active_egress,
        "first_failing_layer": "tcp_connect",
        "destination_port": 7000,
        "attribution_available": False,
        "possible_causes": [
            "trusted_source_policy_drift",
            "pf_or_snort_filter",
            "haproxy_listener_or_accept_pressure",
        ],
        "detail": (
            "FastAPI Cloud did not establish the public TrueNAS TCP connection before "
            "the HTTP probe deadline. This is pre-HTTP evidence: TrueNAS appliance/API "
            "health is independent, while the WAN :7000 ingress requires PF/Snort and "
            "HAProxy correlation for attribution."
        ),
    }
    return {**homelab, "truenas": truenas}
