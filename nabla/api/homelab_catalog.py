"""Typed homelab service catalog for ``/healthz`` and ``/sickz``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from ipaddress import ip_address
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nabla.api.homelab_models import HomelabCatalog, HomelabService

_HOMELAB_CATALOG_PATH = Path(__file__).with_name("data") / "homelab-services.json"
TRUENAS_PUBLIC_HEALTH_URL = "https://truenas.albandrieu.com:7000/"
_PFSENSE_PUBLIC_UI_URL = "https://home.albandrieu.com:10443/"


def fetch_homelab_catalog_sync() -> HomelabCatalog:
    """Load and validate the FastAPI-owned homelab exposure catalog."""
    payload = json.loads(_HOMELAB_CATALOG_PATH.read_text(encoding="utf-8"))
    return HomelabCatalog.model_validate(payload)


async def fetch_homelab_catalog() -> HomelabCatalog:
    """Return the packaged, validated homelab exposure catalog."""
    return fetch_homelab_catalog_sync()


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
    """Return TrueNAS plus explicitly approved public HTTPS services for global health."""
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
    """Resolve catalog ``iconSrc`` against the public site asset location."""
    s = rel.strip()
    if not s:
        return None
    lower = s.lower()
    if lower.startswith("https://") or lower.startswith("http://"):
        return s
    if s.startswith("//"):
        return "https:" + s
    normalized = s.lstrip("/")
    if normalized.startswith("assets/"):
        return f"https://www.albanandrieu.com/{normalized}"
    return s


def _inverse_https_probe_url(service: HomelabService) -> str | None:
    """Return a public HTTPS endpoint only when exposure is explicitly forbidden.

    ``/sickz`` is an inverse reachability check: it should verify that endpoints
    declared ``external=false`` stay unreachable from an external runtime. Internal
    DNS names, private IPs and non-HTTPS endpoints are not Internet exposure targets.
    """
    if service.external or not service.tunnel_url:
        return None

    raw = service.tunnel_url.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None

    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return None
    if host.endswith(".int.albandrieu.com"):
        return None
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        return None

    return _homelab_https_tunnel_key(raw)


def _tunnel_url_to_resolved_icon_src(
    services: Sequence[HomelabService],
    url_for_service: Callable[[HomelabService], str | None],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for service in services:
        url = url_for_service(service)
        if url is None or not service.icon_src:
            continue
        abs_icon = _homelab_resolved_icon_abs(service.icon_src)
        if abs_icon:
            out[_homelab_https_tunnel_key(url)] = abs_icon
    return out


def _tunnel_url_to_service_name(
    services: Sequence[HomelabService],
    url_for_service: Callable[[HomelabService], str | None],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for service in services:
        url = url_for_service(service)
        if url is None:
            continue
        out[_homelab_https_tunnel_key(url)] = service.name
    return out


def homelab_tunnel_url_to_resolved_icon_src(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map explicitly approved public HTTPS endpoints to absolute icon URLs."""
    return _tunnel_url_to_resolved_icon_src(services, lambda service: service.public_https_probe_url)


def homelab_tunnel_url_to_service_name(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map explicitly approved public HTTPS endpoints to catalog service names."""
    return _tunnel_url_to_service_name(services, lambda service: service.public_https_probe_url)


def _homelab_sickz_https_groups_from_services(
    services: Sequence[HomelabService],
) -> list[list[str]]:
    """Return external=false public HTTPS targets that must remain unreachable."""
    groups: list[list[str]] = []
    for service in services:
        url = _inverse_https_probe_url(service)
        if url is None or url == _PFSENSE_PUBLIC_UI_URL:
            continue
        groups.append([url])
    return groups


async def homelab_sickz_catalog_for_sickz() -> tuple[
    list[list[str]],
    dict[str, str],
    dict[str, str],
]:
    """Return inverse targets plus matching icon/name metadata for ``/sickz``."""
    services = await fetch_homelab_services()
    return (
        _homelab_sickz_https_groups_from_services(services),
        _tunnel_url_to_resolved_icon_src(services, _inverse_https_probe_url),
        _tunnel_url_to_service_name(services, _inverse_https_probe_url),
    )


async def homelab_sickz_https_single_url_groups() -> list[list[str]]:
    """Return public HTTPS targets whose catalog policy is ``external=false``."""
    services = await fetch_homelab_services()
    return _homelab_sickz_https_groups_from_services(services)
