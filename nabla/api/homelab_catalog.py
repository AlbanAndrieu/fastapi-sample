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
from nabla.integrations.truenas_client import truenas_url

_log = logging.getLogger(__name__)

HOMELAB_SERVICES_CATALOG_PATH = Path(__file__).with_name("data") / "homelab-services.json"
HOMELAB_EXPOSURE_OVERRIDES_PATH = (
    Path(__file__).with_name("data") / "homelab-exposure-overrides.json"
)

_OVERRIDE_FIELDS = (
    "external",
    "tunnelSecure",
    "endpointEnabled",
    "tunnelTitle",
    "cloudflareAccessRequired",
    "securityException",
)


def _apply_exposure_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply small reviewed policy overrides without rewriting the generated catalog.

    The packaged catalog is intentionally broad and periodically synchronized from the
    website inventory. Security-sensitive exceptions are kept in a separate, auditable
    overlay so intentional direct exposure or a known Cloudflare Access exception cannot
    be lost in a bulk catalog refresh.
    """
    try:
        overrides_payload = json.loads(
            HOMELAB_EXPOSURE_OVERRIDES_PATH.read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return payload
    except (OSError, json.JSONDecodeError) as exc:
        _log.error(
            "Homelab exposure override load failed (%s): %s",
            HOMELAB_EXPOSURE_OVERRIDES_PATH,
            exc,
        )
        return payload

    services = payload.get("services")
    overrides = overrides_payload.get("services")
    if not isinstance(services, list) or not isinstance(overrides, list):
        return payload

    merged = dict(payload)
    merged_services = [dict(item) if isinstance(item, dict) else item for item in services]
    by_name = {
        str(item.get("name") or "").casefold(): item
        for item in merged_services
        if isinstance(item, dict) and item.get("name")
    }

    for override in overrides:
        if not isinstance(override, dict):
            continue
        name = str(override.get("name") or "").strip()
        target = by_name.get(name.casefold())
        if not name or target is None:
            _log.warning("Unknown homelab exposure override target: %s", name or "<empty>")
            continue
        for key in _OVERRIDE_FIELDS:
            if key in override:
                target[key] = override[key]

    merged["services"] = merged_services
    return merged


@lru_cache(maxsize=1)
def _load_homelab_catalog() -> HomelabCatalog:
    """Load the FastAPI-owned exposure catalog and reviewed policy overrides."""
    try:
        payload = json.loads(HOMELAB_SERVICES_CATALOG_PATH.read_text(encoding="utf-8"))
        payload = _apply_exposure_overrides(payload)
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
    configured_truenas_url = truenas_url().rstrip("/") + "/"
    rows: list[tuple[str, str, str, str | None]] = [
        ("albandrieu_truenas", configured_truenas_url, "TrueNAS", None)
    ]
    used_keys: set[str] = {"albandrieu_truenas"}
    for service in services:
        url = service.public_https_probe_url
        if url is None or url == configured_truenas_url:
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
    """Map catalog HTTPS endpoints to icon references used by health-board rows."""
    out: dict[str, str] = {}
    for service in services:
        if not service.tunnel_url or not service.tunnel_url.lower().startswith("https://"):
            continue
        icon_src = _homelab_resolved_icon_abs(service.icon_src or "")
        if icon_src:
            out[_homelab_https_tunnel_key(service.tunnel_url)] = icon_src
    return out


def homelab_tunnel_url_to_service_name(
    services: Sequence[HomelabService],
) -> dict[str, str]:
    """Map catalog HTTPS endpoints to service names used by health-board rows."""
    out: dict[str, str] = {}
    for service in services:
        if not service.tunnel_url or not service.tunnel_url.lower().startswith("https://"):
            continue
        out[_homelab_https_tunnel_key(service.tunnel_url)] = service.name
    return out


def _homelab_sickz_https_groups_from_services(
    services: Sequence[HomelabService],
) -> list[list[str]]:
    """Return every declared HTTPS exposure target for policy-aware ``/sickz``.

    Sickz no longer means simply "this URL must be unreachable". Every catalog
    service participates so the endpoint can compare declared intent (``external``
    and ``tunnelSecure``) with observed HTTP/TLS, TrueNAS runtime and Cloudflare
    Tunnel/Access evidence. The canonical pfSense/Home target is handled separately
    by the dedicated port policy row and is therefore not duplicated here.
    """
    groups: list[list[str]] = []
    for service in services:
        if service.name.casefold() in {"pfsense", "home"}:
            continue
        url = service.tunnel_url
        if not url or not url.lower().startswith("https://"):
            continue
        groups.append([_homelab_https_tunnel_key(url)])
    return groups


async def homelab_sickz_catalog_for_sickz() -> tuple[list[list[str]], dict[str, str], dict[str, str]]:
    """Return policy targets plus icon/name metadata for all catalog HTTPS URLs."""
    services = await fetch_homelab_services()
    return (
        _homelab_sickz_https_groups_from_services(services),
        homelab_tunnel_url_to_resolved_icon_src(services),
        homelab_tunnel_url_to_service_name(services),
    )


async def homelab_sickz_https_single_url_groups() -> list[list[str]]:
    """Return all HTTPS targets used by the exposure-policy checks."""
    services = await fetch_homelab_services()
    return _homelab_sickz_https_groups_from_services(services)
