"""Only SERVICE-allowlisted Backstage v2 health states; never expose raw probes."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from nabla.api import health_board
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


def verified_health_by_service_id(board: object) -> tuple[BoardState, dict[str, State]]:
    """Share the same freshness/ambiguity contract across v2 and public UI.

    Only the exact service ID and four-state result survive. URLs, network
    probes, credentials and security posture never enter this projection.
    """
    if not isinstance(board, dict):
        board = {}
    value = board.get("state")
    board_state: BoardState = value if value in ("fresh", "stale") else "pending"
    homelab = board.get("homelab")
    rows = homelab.get("services") if isinstance(homelab, dict) else None
    rows = rows if isinstance(rows, list) else []
    if board_state != "fresh":
        return board_state, {}

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
    return board_state, {key: _verified_state(row) for key, row in by_id.items() if key not in duplicates}


def project_site_health_v2(
    catalog: SiteArchitectureCatalogV2,
    board: object,
) -> SiteHealthV2:
    """Ambiguous, stale or absent observations yield UNKNOWN, never FAIL."""
    board_state, states = verified_health_by_service_id(board)
    # Health-board rows use service IDs, not unique Backstage entity references.
    # Do not assign one observation to multiple entities with the same name.
    relevant_entities = [
        entity for entity in catalog.entities
        if entity.kind in ("Component", "Resource", "API")
    ]
    name_counts: dict[str, int] = {}
    for entity in relevant_entities:
        name = entity.metadata.name
        name_counts[name] = name_counts.get(name, 0) + 1
    entries = [
        SiteHealthServiceV2(
            entityRef=entity.entityRef,
            state=(
                states.get(entity.metadata.name, "unknown")
                if name_counts[entity.metadata.name] == 1
                else "unknown"
            ),
        )
        for entity in relevant_entities
    ]
    return SiteHealthV2(
        catalogRevision=catalog.catalogRevision,
        boardState=board_state,
        services=entries,
    )


async def fetch_site_health_v2(request: Request) -> SiteHealthV2:
    """Project the shared board snapshot; health_board keeps its provider imports lazy."""
    catalog = await fetch_site_catalog_v2()
    board = await health_board.get_health_board_snapshot(request)
    return project_site_health_v2(catalog, board)
