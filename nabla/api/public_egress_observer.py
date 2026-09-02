"""Bounded observation of this runtime's public egress IP."""

from __future__ import annotations

import ipaddress
import time
from typing import Any

import httpx

_ECHO_URL = "https://checkip.amazonaws.com/"
_TIMEOUT_SEC = 1.5
_CACHE_TTL_SEC = 300.0
_cache: dict[str, Any] = {"ip": None, "observed_at": 0.0}


def _parse_public_ip(raw: str) -> str | None:
    """Return a canonical globally routable IP literal from an echo response."""
    try:
        address = ipaddress.ip_address(raw.strip())
    except ValueError:
        return None
    return str(address) if address.is_global else None


async def _fetch_public_egress_ip() -> str | None:
    timeout = httpx.Timeout(_TIMEOUT_SEC)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"Accept": "text/plain"},
    ) as client:
        response = await client.get(_ECHO_URL)
        response.raise_for_status()
        return _parse_public_ip(response.text)


async def observe_public_egress_ip() -> dict[str, Any]:
    """Return cached non-secret egress telemetry without affecting health state."""
    now = time.monotonic()
    cached_ip = _cache.get("ip")
    cached_at = float(_cache.get("observed_at") or 0.0)
    if isinstance(cached_ip, str) and cached_ip and now - cached_at < _CACHE_TTL_SEC:
        return {
            "ip": cached_ip,
            "observed": True,
            "cached": True,
            "source": "external_echo",
        }

    try:
        observed_ip = await _fetch_public_egress_ip()
    except httpx.HTTPError:
        observed_ip = None

    if observed_ip:
        _cache["ip"] = observed_ip
        _cache["observed_at"] = now
        return {
            "ip": observed_ip,
            "observed": True,
            "cached": False,
            "source": "external_echo",
        }

    return {
        "ip": None,
        "observed": False,
        "cached": False,
        "source": "external_echo",
    }
