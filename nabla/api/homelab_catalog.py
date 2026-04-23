"""Homelab service catalog (HTTPS tunnels) for ``/healthz`` and ``/sickz``."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

_log = logging.getLogger(__name__)

HOMELAB_SERVICES_JSON_URL = "https://www.dr-alban.com/homelab-services.json"
_CACHE_TTL_SEC = 300.0

_cache_lock = asyncio.Lock()


class _HomelabServicesCache:
    """In-process TTL cache for catalog JSON (mutated only under ``_cache_lock``)."""

    __slots__ = ("cached_at", "services")

    def __init__(self) -> None:
        self.services: list[dict[str, Any]] | None = None
        self.cached_at: float = 0.0


_homelab_cache = _HomelabServicesCache()


async def fetch_homelab_services_raw() -> list[dict[str, Any]]:
    """Return ``services`` from the homelab JSON; cached briefly. On failure, last good cache or ``[]``."""
    async with _cache_lock:
        now = time.monotonic()
        if _homelab_cache.services is not None and (now - _homelab_cache.cached_at) < _CACHE_TTL_SEC:
            return _homelab_cache.services
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.get(
                    HOMELAB_SERVICES_JSON_URL,
                    headers={"User-Agent": "nabla-homelab-catalog/1.0"},
                )
                response.raise_for_status()
                data = response.json()
            services = data.get("services") if isinstance(data, dict) else None
            if not isinstance(services, list):
                services = []
            parsed = [s for s in services if isinstance(s, dict)]
        except Exception as exc:
            _log.warning("Homelab catalog fetch failed (%s): %s", HOMELAB_SERVICES_JSON_URL, exc)
            return list(_homelab_cache.services) if _homelab_cache.services is not None else []
        _homelab_cache.services = parsed
        _homelab_cache.cached_at = time.monotonic()
        return parsed


def _healthz_check_key(service_name: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", service_name.lower()).strip("_")
    if not slug:
        slug = f"svc_{index}"
    return f"albandrieu_{slug}"


async def homelab_healthz_probe_rows() -> list[tuple[str, str, str]]:
    """Rows ``(check_key, https_url_with_trailing_slash, display_label)`` for HTTPS tunnel services."""
    services = await fetch_homelab_services_raw()
    rows: list[tuple[str, str, str]] = []
    used_keys: set[str] = set()
    for index, svc in enumerate(services):
        raw_url = str(svc.get("tunnelUrl") or "").strip()
        if not raw_url.lower().startswith("https://"):
            continue
        name = str(svc.get("name") or f"service_{index}").strip() or f"service_{index}"
        key = _healthz_check_key(name, index)
        base = key
        suffix = 2
        while key in used_keys:
            key = f"{base}_{suffix}"
            suffix += 1
        used_keys.add(key)
        url = raw_url.rstrip("/") + "/"
        rows.append((key, url, name))
    return rows


async def homelab_sickz_https_single_url_groups() -> list[list[str]]:
    """One URL per group for ``/sickz`` (inverse reachability); skips pfSense (handled by default targets)."""
    services = await fetch_homelab_services_raw()
    groups: list[list[str]] = []
    for svc in services:
        name = str(svc.get("name") or "").strip().lower()
        if name == "pfsense":
            continue
        raw_url = str(svc.get("tunnelUrl") or "").strip()
        if not raw_url.lower().startswith("https://"):
            continue
        url = raw_url.rstrip("/") + "/"
        groups.append([url])
    return groups
