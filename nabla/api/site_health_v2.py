"""Only SERVICE-allowlisted Backstage v2 health states; never expose raw probes."""
from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    fetch_site_catalog_v2,
)

State = Literal["ok", "warn", "fail", "unknown"]
BoardState = Literal["fresh", "stale", "pending"]
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SiteHealthServiceV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    entityRef: str = Field(pattern=r"^(component|resource|api):[a-z0-9-]+/[a-z0-9-]+$")
    state: State


class SiteHealthV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schemaVersion: Literal[2] = 2
    model: Literal["backstage-health"] = "backstage-health"
    catalogRevision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    boardState: BoardState
    services: list[SiteHealthServiceV2] = Field(max_length=2000)


def _verified_state(row: object) -> State:
    if not isinstance(row, dict):
        return "unknown"
    if row.get("observation_stale") is True or row.get("probe_stale") is True:
        return "unknown"
    state = row.get("effective_state") or row.get("state")
    return state if state in ("ok", "warn", "fail") else "unknown"


def project_site_health_v2(
    catalog: SiteArchitectureCatalogV2, board: object,
) -> SiteHealthV2:
    """Ambiguous, stale or absent observations yield UNKNOWN, never FAIL."""
    if not isinstance(board, dict):
        board = {}
    value = board.get("state")
    board_state: BoardState = value if value in ("fresh", "stale") else "pending"
    homelab = board.get("homelab")
    rows = homelab.get("services") if isinstance(homelab, dict) else None
    rows = rows if isinstance(rows, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("id")
        if not isinstance(key, str) or not _ID.fullmatch(key):
            continue
        if key in by_id:
            duplicates.add(key)
        else:
            by_id[key] = row
    entries = [
        SiteHealthServiceV2(
            entityRef=entity.entityRef,
            state=(
                _verified_state(by_id.get(entity.metadata.name))
                if board_state == "fresh" and entity.metadata.name not in duplicates
                else "unknown"
            ),
        )
        for entity in catalog.entities
        if entity.kind in ("Component", "Resource", "API")
    ]
    return SiteHealthV2(
        catalogRevision=catalog.catalogRevision,
        boardState=board_state,
        services=entries,
    )


async def fetch_site_health_v2(request: Request) -> SiteHealthV2:
    """Keep provider/probe imports lazy until the authenticated request arrives."""
    from nabla.api.health_board import get_health_board_snapshot

    catalog = await fetch_site_catalog_v2()
    board = await get_health_board_snapshot(request)
    return project_site_health_v2(catalog, board)
