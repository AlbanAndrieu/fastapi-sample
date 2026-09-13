"""Reuse rich homelab provider observations for aggregate health composition."""

from __future__ import annotations

from typing import Any

from nabla.api.cloudflare_exposure_observer import CloudflareExposureSnapshot
from nabla.api.platform_health import get_pfsense_api_snapshot

_PFSENSE_LIVENESS_PATH = "/api/v2/system/version"


def cloudflare_health_from_exposure(
    snapshot: CloudflareExposureSnapshot,
) -> dict[str, Any]:
    """Project the rich exposure snapshot onto the lightweight Tunnel health contract."""
    if not snapshot.configured:
        return {
            "reachable": None,
            "api_reachable": None,
            "state": "unknown",
            "status_confirmed": False,
            "degraded": False,
            "effective_state": "warn",
            "severity": "warning",
            "warning": "⚠️ Cloudflare global status could not be confirmed: Cloudflare observer credentials are not configured",
            "error": "Cloudflare observer credentials are not configured",
            "error_kind": "not_configured",
            "probe": "cloudflare_exposure_reuse",
            "skipped": True,
            "reused_from": "cloudflare_exposure",
        }

    statuses = [str(tunnel.status or "unknown").lower() for tunnel in snapshot.tunnels]
    tunnel_confirmed = bool(
        statuses and not snapshot.tunnel_error and not snapshot.stale,
    )
    if not tunnel_confirmed:
        reason = snapshot.refresh_error or snapshot.tunnel_error or "Cloudflare Tunnel inventory is empty or stale"
        return {
            "reachable": None,
            "api_reachable": False if snapshot.tunnel_error else None,
            "state": "unknown",
            "status_confirmed": False,
            "degraded": False,
            "effective_state": "warn",
            "severity": "warning",
            "warning": f"⚠️ Cloudflare global status could not be confirmed: {reason}",
            "error": reason,
            "error_kind": "unconfirmed",
            "probe": "cloudflare_exposure_reuse",
            "stale": snapshot.stale,
            "reused_from": "cloudflare_exposure",
        }

    healthy = sum(status == "healthy" for status in statuses)
    inactive = sum(status == "inactive" for status in statuses)
    degraded_or_down = sum(status in {"degraded", "down"} for status in statuses)
    attention = inactive + degraded_or_down
    all_unhealthy = healthy == 0 and attention > 0
    return {
        "reachable": True,
        "api_reachable": True,
        "state": "warn" if all_unhealthy else "ok",
        "status_confirmed": True,
        "tunnel_count": len(statuses),
        "healthy_tunnels": healthy,
        "inactive_tunnels": inactive,
        "degraded_or_down_tunnels": degraded_or_down,
        "unhealthy_tunnels": attention,
        "tunnel_statuses": statuses,
        "inventory_attention": attention > 0,
        "degraded": all_unhealthy,
        "probe": "cloudflare_exposure_reuse",
        "reused_from": "cloudflare_exposure",
    }


def pfsense_health_from_posture(
    posture: dict[str, Any],
) -> dict[str, Any] | None:
    """Reuse posture only when it already proved the lightweight version endpoint."""
    if posture.get("configured") is not True:
        return {
            "reachable": None,
            "status_confirmed": False,
            "state": "unknown",
            "skipped": True,
            "reason": posture.get("reason") or "pfSense posture observation is not configured",
            "probe": "pfsense_posture_reuse",
            "path": _PFSENSE_LIVENESS_PATH,
            "reused_from": "pfsense_posture",
        }

    endpoint_status = posture.get("endpoint_status")
    endpoint_status = endpoint_status if isinstance(endpoint_status, dict) else {}
    system = endpoint_status.get("system")
    system = system if isinstance(system, dict) else {}
    if system.get("observed") is not True:
        return None

    return {
        "reachable": True,
        "status_confirmed": True,
        "state": "ok",
        "probe": "pfsense_posture_reuse",
        "path": _PFSENSE_LIVENESS_PATH,
        "stale": posture.get("stale") is True,
        "reused_from": "pfsense_posture",
    }


async def platform_checks_from_reconciliation_context(
    context: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Reuse rich request-scoped observations and fall back only when proof is absent."""
    cloudflare = context.get("cloudflare")
    if not isinstance(cloudflare, CloudflareExposureSnapshot):
        raise TypeError("reconciliation context is missing Cloudflare exposure evidence")
    cloudflare_check = cloudflare_health_from_exposure(cloudflare)

    raw_pfsense = context.get("pfsense_dns")
    pfsense_posture = raw_pfsense if isinstance(raw_pfsense, dict) else {}
    pfsense_check = pfsense_health_from_posture(pfsense_posture)
    if pfsense_check is None:
        pfsense_check = await get_pfsense_api_snapshot()

    return {
        "cloudflare": cloudflare_check,
        "pfsense": pfsense_check,
    }


__all__ = [
    "cloudflare_health_from_exposure",
    "pfsense_health_from_posture",
    "platform_checks_from_reconciliation_context",
]
