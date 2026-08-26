"""Typed homelab service catalog for ``/healthz`` and ``/sickz``."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from nabla.api.homelab_models import HomelabCatalog, HomelabService

_log = logging.getLogger(__name__)

HOMELAB_SERVICES_JSON_URL = "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/homelab-services.json"
TRUENAS_PUBLIC_HEALTH_URL = "https://truenas.albandrieu.com:7000/"
_CACHE_TTL_SEC = 300.0

_cache_lock = asyncio.Lock()


class _HomelabCatalogCache:
    """In-process TTL cache for the validated catalog."""

    __slots__ = ("cached_at", "catalog")

    def __init__(self) -> None:
        self.catalog: HomelabCatalog | None = None
        self.cached_at: float = 0.0


_homelab_cache = _HomelabCatalogCache()


async def fetch_homelab_catalog() -> HomelabCatalog:
    """Fetch and validate the homelab catalog, falling back to the last good copy."""
    async with _cache_lock:
        now = time.monotonic()
        if _homelab_cache.catalog is not None and (now - _homelab_cache.cached_at) < _CACHE_TTL_SEC:
            return _homelab_cache.catalog
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.get(
                    HOMELAB_SERVICES_JSON_URL,
                    headers={"User-Agent": "nabla-homelab-catalog/2.0"},
                )
                response.raise_for_status()
                catalog = HomelabCatalog.model_validate(response.json())
        except Exception as exc:
            _log.warning(
                "Homelab catalog fetch/validation failed (%s): %s",
                HOMELAB_SERVICES_JSON_URL,
                exc,
            )
            if _homelab_cache.catalog is not None:
                return _homelab_cache.catalog
            return HomelabCatalog()
        _homelab_cache.catalog = catalog
        _homelab_cache.cached_at = time.monotonic()
        return catalog


async def fetch_homelab_services() -> list[HomelabService]:
    """Return typed homelab services from the validated catalog."""
    return list((await fetch_homelab_catalog()).services)


async def fetch_homelab_services_raw() -> list[dict[str, Any]]:
    """Compatibility view of validated services using the JSON wire-format aliases."""
    services = await fetch_homelab_services()
    return [service.model_dump(mode="json", by_alias=True, exclude_none=True) for service in services]


def _healthz_check_key(service_id: str) -> str:
    """Build the legacy-prefixed health key from the stable service ID."""
    return f"albandrieu_{service_id.replace('-', '_')}"


async def homelab_healthz_probe_rows() -> list[tuple[str, str, str, str | None]]:
    """Return TrueNAS plus approved public HTTPS services for global health."""
    services = await fetch_homelab_services()
    rows: list[tuple[str, str, str, str | None]] = [
        ("albandrieu_truenas", TRUENAS_PUBLIC_HEALTH_URL, "TrueNAS", None),
    ]
    used_keys: set[str] = {"albandrieu_truenas"}
    for service in services:
        url = service.public_https_probe_url
        if url is None or url == TRUENAS_PUBLIC_HEALTH_URL:
            continue
        key = _healthz_check_key(service.service_id)
        base = key
        suffix = 2
        while key in used_keys:
            key = f"{base}_{suffix}"
            suffix += 1
        used_keys.add(key)
        icon_abs = _homelab_resolved_icon_abs(service.icon_src or "")
        rows.append((key, url, service.name, icon_abs))
    return rows


def _homelab_https_tunnel_key(raw_url: str) -> str:
    u = raw_url.strip()
    if not u.lower().startswith("https://"):
        return u
    return u.rstrip("/") + "/"


def _homelab_resolved_icon_abs(rel: str) -> str | None:
    """Turn catalog ``iconSrc`` into an absolute URL for browser contexts."""
    s = rel.strip()
    if not s:
        return None
    lower = s.lower()
    if lower.startswith("https://") or lower.startswith("http://"):
        return s
    if s.startswith("//"):
        return "https:" + s
    # Ne pas faire de urljoin si la base est un chemin filesystem
    if HOMELAB_SERVICES_JSON_URL.startswith("/"):
        return s  # laisser brute, relative à la racine statique locale
    return urljoin(HOMELAB_SERVICES_JSON_URL, s)


def homelab_tunnel_url_to_resolved_icon_src(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map approved public HTTPS endpoints to absolute catalog icon URLs."""
    out: dict[str, str] = {}
    for service in services:
        url = service.public_https_probe_url
        if url is None or not service.icon_src:
            continue
        abs_icon = _homelab_resolved_icon_abs(service.icon_src)
        if abs_icon:
            out[_homelab_https_tunnel_key(url)] = abs_icon
    return out


def homelab_tunnel_url_to_service_name(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map approved public HTTPS endpoints to catalog service names."""
    out: dict[str, str] = {}
    for service in services:
        url = service.public_https_probe_url
        if url is None:
            continue
        out[_homelab_https_tunnel_key(url)] = service.name
    return out


def _homelab_sickz_https_groups_from_services(
    services: Sequence[HomelabService],
) -> list[list[str]]:
    """Return one approved public HTTPS URL per group for ``/sickz``."""
    groups: list[list[str]] = []
    for service in services:
        if service.name.casefold() == "pfsense":
            continue
        url = service.public_https_probe_url
        if url is None:
            continue
        groups.append([_homelab_https_tunnel_key(url)])
    return groups


async def homelab_sickz_catalog_for_sickz() -> tuple[
    list[list[str]],
    dict[str, str],
    dict[str, str],
]:
    """Return sickz groups, resolved icons, and names for approved public services."""
    services = await fetch_homelab_services()
    return (
        _homelab_sickz_https_groups_from_services(services),
        homelab_tunnel_url_to_resolved_icon_src(services),
        homelab_tunnel_url_to_service_name(services),
    )


async def homelab_sickz_https_single_url_groups() -> list[list[str]]:
    """Return approved public HTTPS targets for inverse reachability checks."""
    services = await fetch_homelab_services()
    return _homelab_sickz_https_groups_from_services(services)
