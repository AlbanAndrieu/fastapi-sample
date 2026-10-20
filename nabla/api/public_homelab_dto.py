"""Strict public homelab v1 DTO: only explicitly curated display entries."""

from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "application",
    "ai",
    "storage",
    "security",
    "observability",
    "platform",
    "automation",
    "other",
]


class PublicHomelabServiceV1(BaseModel):
    """No URL, hostname, port, runtime identifier, probe or metric fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    label: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]*$",
    )
    category: Category


class PublicHomelabV1(BaseModel):
    """Minimal, versioned allowlist contract, separate from full topology."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = 1
    services: list[PublicHomelabServiceV1] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def require_unique_ids(self) -> PublicHomelabV1:
        ids = [entry.id for entry in self.services]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate public service ID")
        return self


def load_public_homelab_v1(raw: str | None = None) -> PublicHomelabV1:
    """No configuration publishes []. Invalid configuration never echoes values."""
    if raw is None:
        raw = os.environ.get("PUBLIC_HOMELAB_V1_SERVICES_JSON", "[]")
    if len(raw.encode("utf-8")) > 4096:
        raise RuntimeError("invalid public homelab publication configuration")
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError("expected list")
        return PublicHomelabV1.model_validate({"version": 1, "services": entries})
    except (ValueError, TypeError):
        raise RuntimeError("invalid public homelab publication configuration") from None
