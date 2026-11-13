"""Backstage v2 route intent: projection, fail-closed validation and fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from nabla.api import catalog_routes
from nabla.api import site_architecture_catalog as v2
from nabla.api.catalog_routes import routes_from_catalog, sickz_targets
from nabla.api.homelab_probe_policy import select_probe_subset
from tests.unit.catalog_v2_fixture import catalog, entity, route, routes, service


@pytest.fixture(autouse=True)
def _fresh_route_cache():
    catalog_routes.clear_catalog_routes_cache()
    v2.reset_site_catalog_v2_cache()
    yield
    catalog_routes.clear_catalog_routes_cache()
    v2.reset_site_catalog_v2_cache()


def _snapshot_routes() -> dict[str, catalog_routes.CatalogRoute]:
    return {item.service_id: item for item in routes_from_catalog(v2.load_catalog_snapshot())}


def test_route_identity_is_the_entity_ref_plus_route_name() -> None:
    projected = routes(
        entity(
            "pfsense",
            route("https://pfsense.albandrieu.com", name="admin"),
            route("https://home.albandrieu.com:10443", name="home"),
            kind="Resource",
            title="pfSense",
        ),
    )

    assert [(item.entity_ref, item.route, item.service_id) for item in projected] == [
        ("resource:default/pfsense", "admin", "pfsense"),
        ("resource:default/pfsense", "home", "pfsense-home"),
    ]
    assert [item.name for item in projected] == ["pfSense (admin)", "pfSense (home)"]
    assert projected[1].url == "https://home.albandrieu.com:10443"


def test_public_route_maps_gateway_access_and_probe_path() -> None:
    edge = service(
        "prometheus",
        "https://prometheus.albandrieu.com",
        public=True,
        backend=("172.17.0.24", 9090),
        probe_path="/-/ready",
    )
    direct = service("truenas", "https://truenas.albandrieu.com:7000", public=True, edge="direct", backend=("172.17.0.24", 7000, True))

    assert (edge.cloudflare_edge, edge.access_required) == (True, True)
    assert edge.public_https_probe_url == "https://prometheus.albandrieu.com/-/ready"
    assert (direct.cloudflare_edge, direct.access_required, direct.backend_tls) == (False, False, True)
    assert direct.public_https_probe_url == "https://truenas.albandrieu.com:7000/"


def test_private_route_never_becomes_a_public_probe() -> None:
    private = service("garage", "https://s3.int.albandrieu.com", backend=("172.17.0.24", 3900), risk="LAN only")

    assert private.public is False
    assert private.cloudflare_edge is None
    assert private.public_https_probe_url is None
    assert private.risk_reason == "LAN only"
    assert (private.backend_host, private.backend_port) == ("172.17.0.24", 3900)


@pytest.mark.parametrize(
    "item",
    [
        route(None, public=True),
        route("https://10.0.0.1", public=True),
        route("https://nas.local", public=True),
        route("https://s3.int.albandrieu.com", public=True, access=False),
        route("https://ok.albandrieu.com", probe_path="https://evil.invalid/"),
        route("https://bad host.albandrieu.com"),
    ],
)
def test_malformed_route_intent_fails_closed(item: dict) -> None:
    with pytest.raises(ValidationError):
        routes(entity("broken", item))


def test_ambiguous_route_identity_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate route names"):
        routes(entity("twice", route(name="web"), route(name="web")))
    with pytest.raises(ValueError, match="ambiguous"):
        routes(entity("same", route()), entity("same", route(), kind="Resource"))


def test_sickz_targets_cover_private_hostnames_but_not_pfsense_admin() -> None:
    groups, names, expectations = sickz_targets(
        routes(
            entity("gatus", route("https://gatus.albandrieu.com", public=True), title="Gatus"),
            entity("garage-admin", route("https://garage-admin.albandrieu.com")),
            entity("redis", route()),
            entity("pfsense", route("https://pfsense.albandrieu.com"), kind="Resource"),
        ),
    )

    assert groups == [["https://gatus.albandrieu.com/"], ["https://garage-admin.albandrieu.com/"]]
    assert names["https://gatus.albandrieu.com/"] == "Gatus"
    assert expectations["https://garage-admin.albandrieu.com/"] == {
        "external": False,
        "tunnel_secure": None,
        "expected_reachable": False,
    }


def test_probe_priority_follows_deployment_unit_rank_then_position() -> None:
    projected = routes(
        entity("garage-webui", route("https://garage.albandrieu.com", public=True), rank=0, position=2),
        entity("garage", route(), rank=0, position=0),
        entity("grafana", route("https://grafana.albandrieu.com", public=True), rank=9),
        *(entity(f"app-{index}", route()) for index in range(12)),
    )

    selected = select_probe_subset(projected, limit=6, now=0.0)

    assert [item.service_id for item in selected[:3]] == ["garage", "garage-webui", "grafana"]


@pytest.mark.asyncio
async def test_remote_v2_catalog_is_authoritative(monkeypatch) -> None:
    remote = catalog(entity("gatus", route("https://gatus.albandrieu.com", public=True)))
    fetch = AsyncMock(return_value=remote)
    monkeypatch.setattr(v2, "_download_catalog_v2", fetch)

    first = await catalog_routes.fetch_catalog_routes()
    second = await catalog_routes.fetch_catalog_routes()

    assert [item.service_id for item in first] == ["gatus"] == [item.service_id for item in second]
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_cold_start_failure_uses_the_packaged_snapshot_then_backs_off(monkeypatch) -> None:
    fetch = AsyncMock(side_effect=ValueError("offline"))
    monkeypatch.setattr(v2, "_download_catalog_v2", fetch)

    first = await catalog_routes.fetch_catalog_routes()
    second = await catalog_routes.fetch_catalog_routes()

    assert {item.service_id for item in first} == set(_snapshot_routes())
    assert second == first
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_pre_cutover_catalog_without_exposure_keeps_the_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(v2, "_download_catalog_v2", AsyncMock(return_value=catalog(entity("gatus"))))

    projected = await catalog_routes.fetch_catalog_routes()

    assert {item.service_id for item in projected} == set(_snapshot_routes())


@pytest.mark.asyncio
async def test_refresh_failure_keeps_the_last_known_good_routes(monkeypatch) -> None:
    remote = catalog(entity("gatus", route("https://gatus.albandrieu.com", public=True)))
    monkeypatch.setattr(v2, "_download_catalog_v2", AsyncMock(return_value=remote))
    assert [item.service_id for item in await catalog_routes.fetch_catalog_routes()] == ["gatus"]

    v2.reset_site_catalog_v2_cache()
    monkeypatch.setattr(v2, "_download_catalog_v2", AsyncMock(side_effect=ValueError("offline")))

    assert [item.service_id for item in await catalog_routes.fetch_catalog_routes()] == ["gatus"]


def test_packaged_snapshot_is_a_revision_verified_v2_catalog() -> None:
    raw = v2.load_catalog_snapshot()

    assert v2.project_site_catalog_v2(raw).catalogRevision == raw["catalogRevision"]
    assert "services" not in raw


def test_snapshot_keeps_reviewed_exposure_intent() -> None:
    by_id = _snapshot_routes()

    truenas = by_id["truenas"]
    assert (truenas.public, truenas.cloudflare_edge, truenas.access_required) == (True, False, False)
    assert truenas.public_https_probe_url == "https://truenas.albandrieu.com:7000/"

    s3 = by_id["garage"]
    assert (s3.public, s3.url, s3.backend_port) == (False, "https://s3.int.albandrieu.com", 3900)
    assert s3.risk_reason is not None
    webui = by_id["garage-webui"]
    assert (webui.public, webui.cloudflare_edge, webui.access_required) == (True, True, True)
    assert by_id["garage-admin"].public is False

    assert by_id["prometheus"].public_https_probe_url == "https://prometheus.albandrieu.com/-/ready"
    assert by_id["2fauth"].public_https_probe_url == "https://2fauth.albandrieu.com/"
    # Owner decision: Bitwarden clients cannot pass an Access login (#216).
    assert (by_id["vaultwarden"].public, by_id["vaultwarden"].access_required) == (True, False)


def test_snapshot_pfsense_routes_keep_trusted_source_risk_decisions() -> None:
    by_id = _snapshot_routes()

    for service_id, url in (("pfsense", "https://pfsense.albandrieu.com"), ("pfsense-home", "https://home.albandrieu.com:10443")):
        pfsense = by_id[service_id]
        assert pfsense.entity_ref == "resource:default/pfsense"
        assert (pfsense.public, pfsense.url) == (False, url)
        reason = (pfsense.risk_reason or "").lower()
        assert "source" in reason
        assert "fastapi cloud" in reason
