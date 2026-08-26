"""Typed homelab exposure catalog for ``/healthz`` and ``/sickz``."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nabla.api.homelab_models import HomelabCatalog, HomelabService

_log = logging.getLogger(__name__)

HOMELAB_SERVICES_CATALOG_PATH = Path(__file__).with_name("data") / "homelab-services.json"
TRUENAS_PUBLIC_HEALTH_URL = "https://truenas.albandrieu.com:7000/"


@lru_cache(maxsize=1)
def _load_homelab_catalog() -> HomelabCatalog:
    """Load the FastAPI-owned exposure catalog from the packaged JSON resource."""
    try:
        payload = json.loads(HOMELAB_SERVICES_CATALOG_PATH.read_text(encoding="utf-8"))
        return HomelabCatalog.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        _log.error(
            "Homelab exposure catalog load/validation failed (%s): %s",
            HOMELAB_SERVICES_CATALOG_PATH,
            exc,
        )
        return HomelabCatalog()


async def fetch_homelab_catalog() -> HomelabCatalog:
    """Return the validated FastAPI-owned homelab exposure catalog."""
    return _load_homelab_catalog()


async def fetch_homelab_services() -> list[HomelabService]:
    """Return typed homelab services from the validated exposure catalog."""
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
    """Preserve catalog icon references without reintroducing a website dependency."""
    s = rel.strip()
    if not s:
        return None
    lower = s.lower()
    if lower.startswith("https://") or lower.startswith("http://"):
        return s
    if s.startswith("//"):
        return "https:" + s
    return s


def homelab_tunnel_url_to_resolved_icon_src(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map approved public HTTPS endpoints to catalog icon references."""
    out: dict[str, str] = {}
    for service in services:
        url = service.public_https_probe_url
        if url is None or not service.icon_src:
            continue
        icon_src = _homelab_resolved_icon_abs(service.icon_src)
        if icon_src:
            out[_homelab_https_tunnel_key(url)] = icon_src
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
    """Return sickz groups, icons, and names for approved public services."""
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
