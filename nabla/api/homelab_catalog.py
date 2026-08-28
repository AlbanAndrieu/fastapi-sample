"""Typed homelab exposure catalog for ``/healthz`` and ``/sickz``."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import httpx
from pydantic import ValidationError

from nabla.api.homelab_models import HomelabCatalog, HomelabService
from nabla.integrations.truenas_client import truenas_url

_log = logging.getLogger(__name__)

# nabla-compose owns this contract. The packaged files are retained only as a
# bootstrap/last-known-good snapshot so health endpoints remain useful during a
# transient GitHub outage; they are no longer the authoritative source.
HOMELAB_SERVICES_CATALOG_PATH = Path(__file__).with_name("data") / "homelab-services.json"
HOMELAB_EXPOSURE_OVERRIDES_PATH = (
    Path(__file__).with_name("data") / "homelab-exposure-overrides.json"
)
HOMELAB_SERVICES_CATALOG_URL = os.getenv(
    "HOMELAB_SERVICES_CATALOG_URL",
    "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/homelab-services.json",
).strip()
HOMELAB_EXPOSURE_OVERRIDES_URL = os.getenv(
    "HOMELAB_EXPOSURE_OVERRIDES_URL",
    "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/homelab-exposure-overrides.json",
).strip()

_REMOTE_CACHE_TTL_SECONDS = 300.0
_REMOTE_FAILURE_RETRY_SECONDS = 60.0
_REMOTE_TIMEOUT_SECONDS = 5.0


@dataclass(slots=True)
class _CatalogCacheState:
    """Keep catalog cache value, expiry and provenance consistent as one unit."""

    catalog: HomelabCatalog | None = None
    expires_at: float = 0.0
    source: str = "none"

    def fresh_catalog(self, now: float) -> HomelabCatalog | None:
        """Return the cached catalog only while its monotonic TTL is valid."""
        if self.catalog is not None and now < self.expires_at:
            return self.catalog
        return None

    def store(self, catalog: HomelabCatalog, *, expires_at: float, source: str) -> None:
        """Atomically update the three cache-state fields from one code path."""
        self.catalog = catalog
        self.expires_at = expires_at
        self.source = source

    def reset(self) -> None:
        """Reset the runtime cache to its cold-start state."""
        self.catalog = None
        self.expires_at = 0.0
        self.source = "none"


_catalog_cache_state = _CatalogCacheState()
_catalog_refresh_lock = asyncio.Lock()

_OVERRIDE_FIELDS = (
    "external",
    "tunnelUrl",
    "tunnelSecure",
    "endpointEnabled",
    "tunnelTitle",
    "cloudflareAccessRequired",
    "securityException",
)


def _apply_exposure_overrides(
    payload: dict[str, Any],
    overrides_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply reviewed exposure policy over a generated presentation catalog."""
    if overrides_payload is None:
        try:
            overrides_payload = json.loads(
                HOMELAB_EXPOSURE_OVERRIDES_PATH.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return payload
        except (OSError, json.JSONDecodeError) as exc:
            _log.error(
                "Homelab bootstrap exposure override load failed (%s): %s",
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
def _load_bootstrap_catalog() -> HomelabCatalog:
    """Load the packaged last-known-good snapshot used only as a cold-start fallback."""
    try:
        payload = json.loads(HOMELAB_SERVICES_CATALOG_PATH.read_text(encoding="utf-8"))
        payload = _apply_exposure_overrides(payload)
        return HomelabCatalog.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        _log.error(
            "Homelab bootstrap catalog load/validation failed (%s): %s",
            HOMELAB_SERVICES_CATALOG_PATH,
            exc,
        )
        return HomelabCatalog()


async def _fetch_remote_catalog() -> HomelabCatalog:
    """Fetch and validate the authoritative presentation/exposure contract."""
    if not HOMELAB_SERVICES_CATALOG_URL or not HOMELAB_EXPOSURE_OVERRIDES_URL:
        raise ValueError("authoritative homelab catalog URLs are not configured")

    timeout = httpx.Timeout(_REMOTE_TIMEOUT_SECONDS)
    headers = {
        "Accept": "application/json",
        "User-Agent": "fastapi-sample-homelab-catalog/1",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        services_response, overrides_response = await asyncio.gather(
            client.get(HOMELAB_SERVICES_CATALOG_URL),
            client.get(HOMELAB_EXPOSURE_OVERRIDES_URL),
        )
        services_response.raise_for_status()
        overrides_response.raise_for_status()
        services_payload = services_response.json()
        overrides_payload = overrides_response.json()

    if not isinstance(services_payload, dict) or not isinstance(overrides_payload, dict):
        raise ValueError("authoritative homelab catalog payload must be a JSON object")

    catalog = HomelabCatalog.model_validate(
        _apply_exposure_overrides(services_payload, overrides_payload)
    )
    if not catalog.services:
        raise ValueError("authoritative homelab catalog contains no services")
    return catalog


def clear_homelab_catalog_cache() -> None:
    """Clear runtime and bootstrap caches; intended for tests and explicit refreshes."""
    _catalog_cache_state.reset()
    _load_bootstrap_catalog.cache_clear()


def homelab_catalog_cache_source() -> str:
    """Return sanitized provenance for the current in-process catalog cache."""
    return _catalog_cache_state.source


async def fetch_homelab_catalog() -> HomelabCatalog:
    """Return the remote authoritative catalog with last-known-good fallback semantics."""
    now = time.monotonic()
    cached = _catalog_cache_state.fresh_catalog(now)
    if cached is not None:
        return cached

    # Health and UI requests can arrive together when the cache expires. Serialize
    # the refresh and re-check after acquiring the lock so only one request reaches
    # the authoritative GitHub source per process/TTL window.
    async with _catalog_refresh_lock:
        now = time.monotonic()
        cached = _catalog_cache_state.fresh_catalog(now)
        if cached is not None:
            return cached

        try:
            remote_catalog = await _fetch_remote_catalog()
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            last_known_good = _catalog_cache_state.catalog
            if last_known_good is not None:
                _catalog_cache_state.expires_at = now + _REMOTE_FAILURE_RETRY_SECONDS
                _log.warning(
                    "Authoritative homelab catalog refresh failed; using last-known-good %s catalog: %s",
                    _catalog_cache_state.source,
                    exc,
                )
                return last_known_good

            bootstrap = _load_bootstrap_catalog()
            _catalog_cache_state.store(
                bootstrap,
                expires_at=now + _REMOTE_FAILURE_RETRY_SECONDS,
                source="packaged-bootstrap",
            )
            _log.warning(
                "Authoritative homelab catalog unavailable at cold start; using packaged bootstrap snapshot: %s",
                exc,
            )
            return bootstrap

        _catalog_cache_state.store(
            remote_catalog,
            expires_at=now + _REMOTE_CACHE_TTL_SECONDS,
            source="nabla-compose",
        )
        return remote_catalog


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
        ("albandrieu_truenas", configured_truenas_url, "TrueNAS HTTPS", None)
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
