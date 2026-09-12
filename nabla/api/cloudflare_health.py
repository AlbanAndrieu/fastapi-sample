"""Bounded Cloudflare control-plane health with uncertainty-safe semantics."""

from __future__ import annotations

from typing import Any

import httpx

from nabla.api.cloudflare_tunnels import CloudflareTunnelSettings
from nabla.api.external_probe_cache import ProbeCacheResult, get_or_refresh_probe, reset_probe_cache
from nabla.api.platform_health_diagnostics import http_error_kind, short_error, utc_now
from nabla.api.provider_probe_policies import CLOUDFLARE_TUNNELS_CACHE_POLICY

_CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
_CLOUDFLARE_CACHE_KEY = "cloudflare:tunnels"


def _api_error(response: httpx.Response) -> tuple[str, int | str | None]:
    message = f"Cloudflare Tunnel API returned HTTP {response.status_code}"
    error_code: int | str | None = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
            provider_message = str(first.get("message") or "").strip()
            if provider_message:
                message = provider_message[:240]
            error_code = first.get("code")
    if response.status_code == 404:
        message = f"{message}; verify CLOUDFLARE_ACCOUNT_ID is the Cloudflare Account ID and CLOUDFLARE_API_TOKEN is scoped to that account"
    return message[:480], error_code


def cloudflare_unconfirmed(
    reason: str,
    *,
    error_kind: str,
    api_reachable: bool | None,
    http_status: int | None = None,
    error_code: int | str | None = None,
) -> dict[str, Any]:
    """Represent provider uncertainty without inventing a Cloudflare outage."""
    warning = f"⚠️ Cloudflare global status could not be confirmed: {reason}"
    result: dict[str, Any] = {
        "reachable": None,
        "api_reachable": api_reachable,
        "state": "unknown",
        "status_confirmed": False,
        "degraded": False,
        "severity": "warning",
        "effective_state": "warn",
        "warning": warning,
        "error": reason,
        "error_kind": error_kind,
        "probe": "cloudflare_tunnel_api",
    }
    if http_status is not None:
        result["http_status"] = http_status
    if error_code is not None:
        result["cloudflare_error_code"] = error_code
    return result


async def check_cloudflare_tunnels() -> dict[str, Any]:
    """Check Cloudflare API reachability and report Tunnel inventory separately."""
    settings = CloudflareTunnelSettings.from_environment()
    if settings is None:
        return cloudflare_unconfirmed(
            "Cloudflare observer credentials are not configured",
            error_kind="not_configured",
            api_reachable=None,
        ) | {"skipped": True}

    url = f"{_CLOUDFLARE_API_BASE}/accounts/{settings.account_id}/cfd_tunnel"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.api_token}",
                    "Accept": "application/json",
                },
                params={"is_deleted": "false"},
            )
    except (httpx.HTTPError, OSError) as exc:
        return cloudflare_unconfirmed(
            short_error(exc),
            error_kind=http_error_kind(exc),
            api_reachable=False,
        )

    if response.status_code >= 400:
        reason, error_code = _api_error(response)
        return cloudflare_unconfirmed(
            reason,
            error_kind=f"http_{response.status_code}",
            api_reachable=True,
            http_status=response.status_code,
            error_code=error_code,
        )

    try:
        payload = response.json()
    except ValueError:
        return cloudflare_unconfirmed(
            "Cloudflare Tunnel API returned invalid JSON",
            error_kind="invalid_response",
            api_reachable=True,
            http_status=response.status_code,
        )

    tunnels = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(tunnels, list):
        return cloudflare_unconfirmed(
            "Cloudflare Tunnel API returned an unexpected payload",
            error_kind="invalid_response",
            api_reachable=True,
            http_status=response.status_code,
        )

    statuses = [str(tunnel.get("status") or "unknown").lower() for tunnel in tunnels if isinstance(tunnel, dict)]
    if not statuses:
        return cloudflare_unconfirmed(
            "Cloudflare Tunnel API returned no tunnel inventory",
            error_kind="empty_inventory",
            api_reachable=True,
            http_status=response.status_code,
        )

    healthy = sum(status == "healthy" for status in statuses)
    inactive = sum(status == "inactive" for status in statuses)
    degraded_or_down = sum(status in {"degraded", "down"} for status in statuses)
    attention = inactive + degraded_or_down
    all_unhealthy = healthy == 0 and attention > 0
    return {
        # `reachable` describes the observed Cloudflare control-plane endpoint.
        # Individual Tunnel lifecycle states are reported below and must not turn
        # the provider/API Card red when at least one unrelated/retired Tunnel is inactive.
        "reachable": True,
        "api_reachable": True,
        "http_status": response.status_code,
        "probe": "cloudflare_tunnel_api",
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
        "last_success_at": utc_now(),
    }


def _last_good_reachability(cached: ProbeCacheResult) -> bool | None:
    if cached.last_good is None:
        return None
    reachable = cached.last_good.get("reachable")
    return reachable if isinstance(reachable, bool) else None


async def get_cloudflare_tunnels_snapshot() -> dict[str, Any]:
    """Use cached last-good context while current Cloudflare status is unconfirmed."""
    cached = await get_or_refresh_probe(
        _CLOUDFLARE_CACHE_KEY,
        check_cloudflare_tunnels,
        is_success=lambda value: value.get("status_confirmed") is True,
        policy=CLOUDFLARE_TUNNELS_CACHE_POLICY,
    )
    current = dict(cached.value)
    current.update(cached.metadata)
    if current.get("status_confirmed") is True and cached.metadata.get("stale") is not True:
        return current

    reason = str(
        current.get("refresh_error") or current.get("error") or current.get("reason") or "Cloudflare control-plane evidence is stale or unavailable",
    )
    result = cloudflare_unconfirmed(
        reason,
        error_kind=str(current.get("error_kind") or "unconfirmed"),
        api_reachable=current.get("api_reachable"),
        http_status=(int(current["http_status"]) if isinstance(current.get("http_status"), int) else None),
        error_code=current.get("cloudflare_error_code"),
    )
    result.update(cached.metadata)
    result["stale"] = cached.metadata.get("stale") is True or cached.last_good is not None
    last_known = _last_good_reachability(cached)
    if last_known is not None:
        result["last_known_reachable"] = last_known
    if current.get("skipped") is True:
        result["skipped"] = True
    return result


async def reset_cloudflare_api_cache() -> None:
    """Reset Cloudflare provider cache for deterministic tests."""
    await reset_probe_cache(_CLOUDFLARE_CACHE_KEY)
