"""Temporary public *minimal* service overview for the FastAPI landing page.

This is intentionally separate from OWNER and SERVICE diagnostic endpoints.
Only reviewed Backstage labels and four-valued summarized health are projected.
No URLs, IPs, ports, dependencies, security posture or probe evidence escape.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from nabla.api import health_board
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    fetch_site_catalog_v2,
)
from nabla.api.site_health_v2 import project_site_health_v2

State = Literal["ok", "warn", "fail", "unknown"]
Kind = Literal["API", "Component", "Resource"]
BoardState = Literal["fresh", "stale", "pending"]


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
    services: list[PublicUiService] = Field(max_length=2000)


def public_ui_services_enabled() -> bool:
    """Temporary operator-approved disclosure; switch off without code changes."""
    return os.getenv("HOMELAB_UI_PUBLIC_SERVICES_ENABLED", "true").strip().lower() == "true"


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


async def get_public_ui_services(request: Request) -> PublicUiServices:
    """Read shared bounded server cache; no browser auth, no raw probe output."""
    catalog = await fetch_site_catalog_v2()
    try:
        board = await health_board.get_health_board_snapshot(request)
    except Exception:
        # The service directory should survive failures in optional diagnostic
        # collectors. No fresh evidence means UNKNOWN, never fabricated OK/FAIL.
        board = {"state": "pending"}
    return project_public_ui_services(catalog, board)
