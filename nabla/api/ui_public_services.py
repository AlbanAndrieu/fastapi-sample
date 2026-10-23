"""Temporary public *minimal* service overview for the FastAPI landing page.

This is intentionally separate from OWNER and SERVICE diagnostic endpoints.
Only reviewed Backstage labels and four-valued summarized health are projected.
No URLs, IPs, ports, dependencies, security posture or probe evidence escape.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import re
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from nabla.api import health_board
from nabla.api.homelab_catalog import packaged_homelab_catalog
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteCatalogV2Unavailable,
    fetch_site_catalog_v2,
)
from nabla.api.site_health_v2 import project_site_health_v2, verified_health_by_service_id

State = Literal["ok", "warn", "fail", "unknown"]
Kind = Literal["API", "Component", "Resource"]
BoardState = Literal["fresh", "stale", "pending"]
CatalogSource = Literal["backstage-v2", "bootstrap-snapshot"]
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()+&-]{0,127}$")
_IP_LABEL = re.compile(r"\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b")


class PublicUiService(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: str = Field(min_length=1, max_length=128)
    kind: Kind
    state: State


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
        )
        for entity in catalog.entities
        if entity.kind in ("API", "Component", "Resource")
    ]
    return PublicUiServices(
        catalogRevision=catalog.catalogRevision,
        boardState=health.boardState,
        services=services,
    )


async def _bootstrap_public_service_directory(request: Request) -> PublicUiServices:
    """Fail-safe packaged inventory when the canonical v2 source is unreachable.

    These are *labels only*, explicitly identified as a stale bootstrap snapshot.
    No internal URI, IP, port, runtime detail, or unverified state is serialized.
    """
    catalog = packaged_homelab_catalog()
    try:
        board = await health_board.get_health_board_snapshot(request)
    except Exception:
        board = {"state": "pending"}
    board_state, states = verified_health_by_service_id(board)
    by_label: dict[str, list[str]] = {}
    for service in catalog.services:
        label = service.name.strip()
        if _SAFE_LABEL.fullmatch(label) and not _IP_LABEL.search(label):
            by_label.setdefault(label, []).append(service.service_id)
    services = [
        PublicUiService(
            name=name,
            kind="Component",
            state=states.get(identifiers[0], "unknown") if len(identifiers) == 1 else "unknown",
        )
        for name, identifiers in sorted(by_label.items(), key=lambda entry: entry[0].casefold())[:2000]
    ]
    if not services:
        # Do not fabricate service names when neither source is available.
        raise SiteCatalogV2Unavailable("No verified public labels are available")
    serialized = json.dumps(
        [(service.name, service.kind) for service in services],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return PublicUiServices(
        catalogRevision="sha256:" + hashlib.sha256(serialized).hexdigest(),
        boardState=board_state,
        catalogSource="bootstrap-snapshot",
        services=services,
    )


_backstage_retry_after: float = 0.0


async def get_public_ui_services(request: Request) -> PublicUiServices:
    """Read shared bounded server cache; no browser auth, no raw probe output."""
    global _backstage_retry_after
    if time.monotonic() < _backstage_retry_after:
        return await _bootstrap_public_service_directory(request)
    try:
        catalog = await fetch_site_catalog_v2()
    except SiteCatalogV2Unavailable:
        # Bound repeated failed GitHub attempts across anonymous UI refreshes.
        _backstage_retry_after = time.monotonic() + 60.0
        return await _bootstrap_public_service_directory()
    _backstage_retry_after = 0.0
    try:
        board = await health_board.get_health_board_snapshot(request)
    except Exception:
        # The service directory should survive failures in optional diagnostic
        # collectors. No fresh evidence means UNKNOWN, never fabricated OK/FAIL.
        board = {"state": "pending"}
    return project_public_ui_services(catalog, board)
