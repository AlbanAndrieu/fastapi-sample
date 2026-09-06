"""Declared homelab services generated from nabla-compose x-nabla metadata."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

DECLARED_SERVICES_URL = (
    "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/"
    "master/catalog/services.json"
)
_CACHE_TTL_SEC = 300.0
_log = logging.getLogger(__name__)
_cache_lock = asyncio.Lock()
_cached_at = 0.0
_cached_catalog: "DeclaredServiceCatalog | None" = None


class RuntimeBinding(BaseModel):
    """Explicit link between a declared service and its runtime provider."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    provider: Literal["truenas-app", "logical", "external", "host"]
    app_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("appId", "app_id"),
        serialization_alias="appId",
    )
    container_service: str | None = Field(
        default=None,
        validation_alias=AliasChoices("containerService", "container_service"),
        serialization_alias="containerService",
    )

    @model_validator(mode="after")
    def require_truenas_identity(self) -> "RuntimeBinding":
        """TrueNAS bindings must provide deterministic app or Compose-service identity."""
        if self.provider == "truenas-app" and not (
            self.app_id or self.container_service
        ):
            raise ValueError("truenas-app runtime requires appId or containerService")
        return self


class DeclaredService(BaseModel):
    """One code-owned service declaration from nabla-compose."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    service_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        validation_alias=AliasChoices("id", "serviceId", "service_id"),
        serialization_alias="id",
    )
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_path: str = Field(
        min_length=1,
        validation_alias=AliasChoices("sourcePath", "source_path"),
        serialization_alias="sourcePath",
    )
    compose_service: str = Field(
        min_length=1,
        validation_alias=AliasChoices("composeService", "compose_service"),
        serialization_alias="composeService",
    )
    presentation_role: Literal["service", "core", "support"] | None = Field(
        default=None,
        validation_alias=AliasChoices("presentationRole", "presentation_role"),
        serialization_alias="presentationRole",
    )
    criticality: Literal["critical", "high", "medium", "low"] | None = None
    security_functions: list[
        Literal["govern", "identify", "protect", "detect", "respond", "recover"]
    ] | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("securityFunctions", "security_functions"),
        serialization_alias="securityFunctions",
    )
    url: str | None = None
    description: str | None = None
    icon: str | None = Field(default=None, min_length=1, max_length=32)
    runtime: RuntimeBinding | None = None

    @model_validator(mode="after")
    def require_unique_security_functions(self) -> "DeclaredService":
        """Reject ambiguous duplicate NIST CSF function metadata."""
        if self.security_functions is not None and len(self.security_functions) != len(
            set(self.security_functions)
        ):
            raise ValueError("securityFunctions must not contain duplicates")
        return self


class DeclaredServiceCatalog(BaseModel):
    """Versioned declared inventory generated with the topology catalog."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    version: int = Field(ge=1)
    catalog_revision: str = Field(
        min_length=1,
        validation_alias=AliasChoices("catalogRevision", "catalog_revision"),
        serialization_alias="catalogRevision",
    )
    topology_version: int = Field(
        ge=1,
        validation_alias=AliasChoices("topologyVersion", "topology_version"),
        serialization_alias="topologyVersion",
    )
    name: str = Field(min_length=1)
    services: list[DeclaredService] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "DeclaredServiceCatalog":
        ids = [service.service_id for service in self.services]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate declared service id")
        return self


async def fetch_declared_service_catalog() -> DeclaredServiceCatalog:
    """Fetch the code-owned catalog, retaining the last known good copy."""
    global _cached_at, _cached_catalog

    async with _cache_lock:
        now = time.monotonic()
        if _cached_catalog is not None and now - _cached_at < _CACHE_TTL_SEC:
            return _cached_catalog
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.get(
                    DECLARED_SERVICES_URL,
                    headers={"User-Agent": "nabla-declared-services/1.0"},
                )
                response.raise_for_status()
                catalog = DeclaredServiceCatalog.model_validate(response.json())
        except Exception as exc:
            _log.warning(
                "Declared service catalog fetch/validation failed (%s): %s",
                DECLARED_SERVICES_URL,
                exc,
            )
            if _cached_catalog is not None:
                return _cached_catalog
            return DeclaredServiceCatalog(
                version=1,
                catalogRevision="unavailable",
                topologyVersion=1,
                name="Nabla homelab declared services",
            )
        _cached_catalog = catalog
        _cached_at = time.monotonic()
        return catalog
