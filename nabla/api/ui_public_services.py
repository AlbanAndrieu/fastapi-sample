"""Temporary public *minimal* service overview for the FastAPI landing page.

This is intentionally separate from OWNER and SERVICE diagnostic endpoints.
Only reviewed Backstage labels and four-valued summarized health are projected.
No URLs, IPs, ports, dependencies, security posture or probe evidence escape.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated, Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from nabla.api import health_board, public_status_light, public_status_relay
from nabla.api.ui_public_directory_redis import (
    read_public_directory_redis,
    write_public_directory_redis,
)
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteCatalogV2Unavailable,
    fetch_site_catalog_v2,
    fetch_catalog_v2_source,
    load_catalog_snapshot,
    project_site_catalog_v2,
)
from nabla.api.site_health_v2 import project_site_health_v2, verified_health_by_service_id
from nabla.api.runtime_environment import fastapi_cloud_runtime_detected

State = Literal["ok", "warn", "fail", "unknown", "scheduled"]
Kind = Literal["API", "Component", "Resource"]
BoardState = Literal["fresh", "stale", "pending"]
CatalogSource = Literal["backstage-v2", "bootstrap-snapshot"]


class PublicUiService(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: str = Field(min_length=1, max_length=128)
    kind: Kind
    state: State
    # Reviewed Backstage metadata only. Never expose entityRef, routes or owners.
    serviceType: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    tags: list[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]] = Field(default_factory=list, max_length=3)


class PublicUiServices(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schemaVersion: Literal[2] = 2
    model: Literal["public-service-overview"] = "public-service-overview"
    catalogRevision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    boardState: BoardState
    catalogSource: CatalogSource = "backstage-v2"
    services: list[PublicUiService] = Field(max_length=2000)


def public_ui_services_enabled() -> bool:
    """Temporary operator-approved disclosure; switch off without code changes."""
    # Old HOMELAB_UI_PUBLIC_SERVICES_ENABLED is deliberately superseded:
    # a stale Cloud setting must not accidentally hide the read-only view.
    return os.getenv("HOMELAB_UI_PUBLIC_READONLY_ENABLED", "true").strip().lower() == "true"


def project_public_ui_services(
    catalog: SiteArchitectureCatalogV2,
    board: object,
) -> PublicUiServices:
    """Never serialize operational properties even when the input contains them."""
    health = project_site_health_v2(catalog, board)
    states = {entry.entityRef: entry.state for entry in health.services}
    services = [
        PublicUiService(
            name=entity.metadata.title or entity.metadata.name,
            kind=entity.kind,
            state=states.get(entity.entityRef, "unknown"),
            serviceType=entity.spec.get("type"),
            tags=(entity.metadata.tags or [])[:3],
        )
        for entity in catalog.entities
        if entity.kind in ("API", "Component", "Resource")
    ]
    return PublicUiServices(
        catalogRevision=catalog.catalogRevision,
        boardState=health.boardState,
        services=services,
    )


def _public_board_reader(request: Request):
    """Cloud anonymous reads remain passive unless expressly enabled.

    An authorized diagnostic endpoint still uses get_health_board_snapshot()
    and can refresh the board. Do not turn an anonymous catalogue hit into
    a costly multi-provider reconciliation on a scale-to-zero replica.
    """
    hostname = request.url.hostname if request is not None else None
    cloud = fastapi_cloud_runtime_detected(hostname)
    allow_expensive = os.getenv("FASTAPI_CLOUD_PUBLIC_DEEP_PROBES_ENABLED", "").strip().lower() == "true"
    if cloud and not allow_expensive:
        return health_board.peek_public_health_board_snapshot(request)
    return health_board.get_health_board_snapshot(request)


async def _bootstrap_public_service_directory(request: Request) -> PublicUiServices:
    """Fail-safe packaged Backstage v2 snapshot when the live source is unreachable.

    Same sanitized projection as the live catalog, explicitly identified as a
    bootstrap snapshot. No internal URI, IP, port or runtime detail is serialized.
    """
    try:
        board = await asyncio.wait_for(
            _public_board_reader(request),
            timeout=_PUBLIC_BOARD_DEADLINE_SECONDS,
        )
    except Exception:
        board = {"state": "pending"}
    board_state, _ = verified_health_by_service_id(board)
    if board_state != "fresh":
        # A shared L2 entry is ONLY an inventory with UNKNOWN health. When
        # in-process health is fresh, prefer real states from the snapshot.
        cached = await read_public_directory_redis()
        if cached is not None:
            return cached
    # Loaded only after the Redis short-circuit: a shared inventory needs no bootstrap.
    try:
        catalog = project_site_catalog_v2(load_catalog_snapshot())
    except (OSError, ValueError) as exc:
        # Do not fabricate service names when neither source is available.
        raise SiteCatalogV2Unavailable("No verified public labels are available") from exc
    return project_public_ui_services(catalog, board).model_copy(
        update={"catalogSource": "bootstrap-snapshot"},
    )


_BACKSTAGE_RETRY_SECONDS = 60.0
# The public catalogue must not inherit the 5s Backstage HTTP timeout.
# These two independent caps keep the anonymous landing responsive when
# Backstage or the cached health board stalls.
_PUBLIC_CATALOG_DEADLINE_SECONDS = 1.5
_PUBLIC_BOARD_DEADLINE_SECONDS = 0.7
# Monotonic deadline before the next Backstage attempt; shared by all requests.
_backstage_backoff: dict[str, float] = {"retry_after": 0.0}


async def get_public_ui_services(request: Request) -> PublicUiServices:
    """Read shared bounded server cache; no browser auth, no raw probe output."""
    if time.monotonic() < _backstage_backoff["retry_after"]:
        return await _bootstrap_public_service_directory(request)
    try:
        catalog = await asyncio.wait_for(
            fetch_site_catalog_v2(),
            timeout=_PUBLIC_CATALOG_DEADLINE_SECONDS,
        )
    except (SiteCatalogV2Unavailable, TimeoutError):
        # Bound repeated failed GitHub attempts across anonymous UI refreshes.
        _backstage_backoff["retry_after"] = time.monotonic() + _BACKSTAGE_RETRY_SECONDS
        return await _bootstrap_public_service_directory(request)
    _backstage_backoff["retry_after"] = 0.0
    try:
        board = await asyncio.wait_for(
            _public_board_reader(request),
            timeout=_PUBLIC_BOARD_DEADLINE_SECONDS,
        )
    except Exception:
        # The service directory should survive failures in optional diagnostic
        # collectors. No fresh evidence means UNKNOWN, never fabricated OK/FAIL.
        board = {"state": "pending"}
    projected = project_public_ui_services(catalog, board)
    # Light public HTTP is NOT the deep Cloud fan-out. It samples at most six
    # approved HTTPS targets per three minutes without delaying this request.
    # A cold replica returns UNKNOWN initially, then gets real per-service
    # public HTTP states on the next passive refresh.
    hostname = request.url.hostname if request is not None else None
    cloud = fastapi_cloud_runtime_detected(hostname)
    light_enabled = os.getenv("FASTAPI_CLOUD_PUBLIC_LIGHT_PROBES_ENABLED", "true").strip().lower() == "true"
    deep_enabled = os.getenv("FASTAPI_CLOUD_PUBLIC_DEEP_PROBES_ENABLED", "").strip().lower() == "true"
    if cloud and light_enabled and not deep_enabled:
        try:
            raw = await asyncio.wait_for(fetch_catalog_v2_source(), timeout=0.15)
            public_status_light.start_light_public_checks(catalog.catalogRevision, raw)
        except (SiteCatalogV2Unavailable, TimeoutError):
            pass  # Never block public inventory on the optional light wave.
        light_states = public_status_light.fresh_public_states(catalog.catalogRevision)
        if light_states:
            # Preserve a confirmed full-board or scheduled result; never
            # infer internal service state from the public HTTP vantage.
            name_to_ref = {entity.metadata.title or entity.metadata.name: entity.entityRef for entity in catalog.entities if entity.kind in ("API", "Component", "Resource")}
            counts: dict[str, int] = {}
            for entity in catalog.entities:
                if entity.kind in ("API", "Component", "Resource"):
                    name = entity.metadata.title or entity.metadata.name
                    counts[name] = counts.get(name, 0) + 1
            services = [
                service.model_copy(update={"state": light_states[name_to_ref[service.name]]})
                if counts.get(service.name) == 1 and service.state == "unknown" and name_to_ref.get(service.name) in light_states
                else service
                for service in projected.services
            ]
            if services != projected.services:
                # Fresh means at least one *recent PUBLIC HTTP* observation,
                # not that the internal homelab or every service is healthy.
                projected = projected.model_copy(update={"services": services, "boardState": "fresh"})
    if cloud:
        relayed = await public_status_relay.read_states(catalog.catalogRevision)
        if relayed:
            # Only names already present in the reviewed public v2 projection
            # may receive a LAN verdict. An ambiguous ID is never assigned.
            counts: dict[str, int] = {}
            for entity in catalog.entities:
                if entity.kind in ("API", "Component", "Resource"):
                    counts[entity.metadata.name] = counts.get(entity.metadata.name, 0) + 1
            ref_to_name = {
                entity.metadata.name: entity.metadata.title or entity.metadata.name
                for entity in catalog.entities
                if entity.kind in ("API", "Component", "Resource") and counts.get(entity.metadata.name) == 1
            }
            reverse = {name: ident for ident, name in ref_to_name.items()}
            if len(reverse) == len(ref_to_name):
                services = [
                    service.model_copy(update={"state": relayed[reverse[service.name]]}) if service.name in reverse and reverse[service.name] in relayed else service
                    for service in projected.services
                ]
                if services != projected.services:
                    projected = projected.model_copy(update={"services": services, "boardState": "fresh"})
    # L2 is opt-in, bounded to 150ms, and stores labels only; fail open to L1.
    await write_public_directory_redis(projected)
    return projected
