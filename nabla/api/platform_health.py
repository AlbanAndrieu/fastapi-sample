"""Optional platform API health probes for Cloudflare Tunnel and pfSense."""

from __future__ import annotations

import os
from typing import Any

import httpx

_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
_PFSENSE_STATUS_PATH = "/api/v2/status/system"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _short_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240]


async def check_cloudflare_tunnels() -> dict[str, Any]:
    """Check Cloudflare Tunnel control-plane health with read-only credentials."""
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are not configured",
            "probe": "cloudflare_tunnel_api",
        }

    url = f"{_CLOUDFLARE_API_BASE}/accounts/{account_id}/cfd_tunnel"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Accept": "application/json",
                },
                params={"is_deleted": "false"},
            )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return {
            "reachable": False,
            "error": _short_error(exc),
            "probe": "cloudflare_tunnel_api",
        }

    tunnels = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(tunnels, list):
        return {
            "reachable": False,
            "error": "Cloudflare Tunnel API returned an unexpected payload",
            "probe": "cloudflare_tunnel_api",
        }

    statuses = [
        str(tunnel.get("status") or "unknown").lower()
        for tunnel in tunnels
        if isinstance(tunnel, dict)
    ]
    unhealthy = [status for status in statuses if status in {"inactive", "degraded", "down"}]
    healthy = sum(status == "healthy" for status in statuses)
    return {
        "reachable": True,
        "http_status": response.status_code,
        "probe": "cloudflare_tunnel_api",
        "tunnel_count": len(statuses),
        "healthy_tunnels": healthy,
        "unhealthy_tunnels": len(unhealthy),
        "tunnel_statuses": statuses,
        "degraded": bool(unhealthy),
    }


async def check_pfsense_api() -> dict[str, Any]:
    """Check the configured pfSense REST API v2 status endpoint read-only."""
    base_url = os.getenv("PFSENSE_API_URL", "").strip().rstrip("/")
    api_key = os.getenv("PFSENSE_API_KEY", "").strip()
    if not base_url or not api_key:
        return {
            "reachable": None,
            "skipped": True,
            "reason": "PFSENSE_API_URL and PFSENSE_API_KEY are not configured",
            "probe": "pfsense_rest_api_v2",
        }

    verify_ssl = os.getenv("PFSENSE_API_VERIFY_SSL", "true").strip().lower() in _TRUE_VALUES
    url = f"{base_url}{_PFSENSE_STATUS_PATH}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=verify_ssl,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                headers={"X-API-Key": api_key, "Accept": "application/json"},
            )
    except (httpx.HTTPError, OSError) as exc:
        return {
            "reachable": False,
            "error": _short_error(exc),
            "probe": "pfsense_rest_api_v2",
            "url": url,
        }

    result: dict[str, Any] = {
        "reachable": response.status_code < 500,
        "http_status": response.status_code,
        "probe": "pfsense_rest_api_v2",
        "url": url,
        "tls_trusted": True if verify_ssl and url.lower().startswith("https://") else None,
    }
    if response.status_code >= 400:
        result["error"] = f"pfSense API returned HTTP {response.status_code}"
    return result
