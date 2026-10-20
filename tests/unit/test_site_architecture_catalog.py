"""The site catalogue never leaks owner fields or uses a stale fallback."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from nabla.api import homelab_catalog
from nabla.api.homelab_models import HomelabCatalog
from nabla.api.site_architecture_catalog import SiteArchitectureCatalogV1, site_architecture_catalog


OWNER_CATALOG = HomelabCatalog.model_validate(
    {
        "version": 2,
        "services": [
            {
                "id": "garage-admin",
                "name": "Garage Admin",
                "internalHost": "172.17.0.24",
                "internalPort": 3903,
                "tunnelUrl": "https://garage-admin.albandrieu.com",
                "external": False,
                "cloudflareAccessRequired": True,
                "healthNote": "sensitive private telemetry",
            },
        ],
    },
)


def test_site_catalog_is_a_strict_allowlist() -> None:
    result = site_architecture_catalog(OWNER_CATALOG).model_dump(mode="json")
    assert result == {"version": 1, "services": [{"id": "garage-admin", "name": "Garage Admin"}]}
    with pytest.raises(ValidationError):
        SiteArchitectureCatalogV1.model_validate(
            {"version": 1, "services": [{"id": "garage-admin", "name": "Garage Admin", "internalHost": "172.17.0.24"}]},
        )
    with pytest.raises(ValidationError):
        site_architecture_catalog(HomelabCatalog())
    with pytest.raises(ValidationError):
        SiteArchitectureCatalogV1.model_validate(
            {"version": 1, "services": [{"id": "private", "name": "172.17.0.24:8091"}]},
        )


@pytest.mark.asyncio
async def test_site_catalog_fails_without_authoritative_data(monkeypatch) -> None:
    homelab_catalog.clear_homelab_catalog_cache()
    homelab_catalog._catalog_cache_state.store(
        OWNER_CATALOG, expires_at=time.monotonic() + 60, source="packaged-bootstrap",
    )
    failing = AsyncMock(side_effect=httpx.ConnectError("remote unavailable"))
    monkeypatch.setattr(homelab_catalog, "_fetch_remote_catalog", failing)
    with pytest.raises(homelab_catalog.AuthoritativeCatalogUnavailable):
        await homelab_catalog.fetch_authoritative_homelab_catalog()
    assert failing.await_count == 1
    homelab_catalog.clear_homelab_catalog_cache()


@pytest.mark.asyncio
async def test_site_catalog_accepts_recent_authoritative_cache_only(monkeypatch) -> None:
    homelab_catalog.clear_homelab_catalog_cache()
    fetch = AsyncMock(return_value=OWNER_CATALOG)
    monkeypatch.setattr(homelab_catalog, "_fetch_remote_catalog", fetch)
    first = await homelab_catalog.fetch_authoritative_homelab_catalog()
    second = await homelab_catalog.fetch_authoritative_homelab_catalog()
    assert first is second
    assert fetch.await_count == 1
    homelab_catalog._catalog_cache_state.last_verified_at -= 301
    fetch.side_effect = httpx.TimeoutException("unavailable")
    with pytest.raises(homelab_catalog.AuthoritativeCatalogUnavailable):
        await homelab_catalog.fetch_authoritative_homelab_catalog()
    assert fetch.await_count == 2
    homelab_catalog.clear_homelab_catalog_cache()
