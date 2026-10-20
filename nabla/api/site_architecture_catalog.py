"""Read-only, allowlisted site architecture catalogue (no LAN details)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nabla.api.homelab_models import HomelabCatalog


class SiteArchitectureServiceV1(BaseModel):
    """Presentation identity only; no endpoints or security policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def require_plain_display_label(cls, value: str) -> str:
        """Names are display labels, not destinations, addresses or credentials."""
        if re.search(r"https?://|(?:\d{1,3}\.){3}\d{1,3}|\.int\.|[:/\\@]", value, re.I):
            raise ValueError("site display name contains endpoint material")
        return value


class SiteArchitectureCatalogV1(BaseModel):
    """Authenticated site-only consumer contract, from the authoritative source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = 1
    services: list[SiteArchitectureServiceV1] = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def unique_identities(self) -> SiteArchitectureCatalogV1:
        identifiers = [service.id for service in self.services]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate site architecture identities")
        return self


def site_architecture_catalog(catalog: HomelabCatalog) -> SiteArchitectureCatalogV1:
    """Build a strict projection; never serialize the raw catalog."""
    return SiteArchitectureCatalogV1(
        services=[
            SiteArchitectureServiceV1(id=service.service_id, name=service.name)
            for service in catalog.services
        ],
    )
