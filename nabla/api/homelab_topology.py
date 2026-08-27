"""Typed declared homelab topology sourced from nabla-compose."""

from __future__ import annotations

import asyncio
from enum import StrEnum
import logging
import time

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

HOMELAB_TOPOLOGY_URL = "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/service-topology.json"
_CACHE_TTL_SEC = 300.0
_log = logging.getLogger(__name__)
_cache_lock = asyncio.Lock()


class HomelabRelationType(StrEnum):
    """Supported design-time relationships between homelab components."""

    DEPENDS_ON = "dependsOn"
    CONSUMES_API = "consumesApi"
    PROVIDES_API = "providesApi"
    PART_OF = "partOf"
    ROUTES_TO = "routesTo"
    OBSERVED_BY = "observedBy"
    STORES_IN = "storesIn"
    AUTHENTICATES_VIA = "authenticatesVia"
    EXPOSED_BY = "exposedBy"
    AUTOMATES = "automates"


class HomelabRelationStrength(StrEnum):
    """Whether a declared integration is essential to the described capability."""

    REQUIRED = "required"
    OPTIONAL = "optional"


class HomelabTopologyNode(BaseModel):
    """One component participating in the declared topology."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=64)
    source_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        validation_alias=AliasChoices("sourcePath", "source_path"),
        serialization_alias="sourcePath",
    )
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=1024)
    icon: str | None = Field(default=None, min_length=1, max_length=32)


class HomelabTopologyRelation(BaseModel):
    """A directional relation backed by one or more configuration references."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    target: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    type: HomelabRelationType
    strength: HomelabRelationStrength
    description: str | None = Field(default=None, max_length=1024)
    evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_self_relation(self) -> HomelabTopologyRelation:
        """A component cannot declare a topology edge to itself."""
        if self.source == self.target:
            raise ValueError("topology relation source and target must differ")
        return self


class HomelabTopology(BaseModel):
    """Versioned declared service graph consumed by APIs and visualization clients."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    version: int = Field(default=1, ge=1)
    name: str = Field(default="Nabla homelab declared topology", min_length=1)
    nodes: list[HomelabTopologyNode] = Field(default_factory=list)
    relations: list[HomelabTopologyRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> HomelabTopology:
        """Require unique nodes and relations that reference declared node IDs."""
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate homelab topology node id")

        known = set(node_ids)
        relation_keys: set[tuple[str, str, HomelabRelationType]] = set()
        for relation in self.relations:
            if relation.source not in known or relation.target not in known:
                raise ValueError(
                    f"topology relation references an unknown node: {relation.source} -> {relation.target}",
                )
            key = (relation.source, relation.target, relation.type)
            if key in relation_keys:
                raise ValueError(
                    f"duplicate homelab topology relation: {relation.source} -> {relation.target} ({relation.type})",
                )
            relation_keys.add(key)
        return self


class _TopologyCache:
    """Last-known-good topology plus monotonic cache timestamp."""

    __slots__ = ("cached_at", "topology")

    def __init__(self) -> None:
        self.topology: HomelabTopology | None = None
        self.cached_at = 0.0


_topology_cache = _TopologyCache()


async def fetch_homelab_topology() -> HomelabTopology:
    """Fetch declared topology, retaining the last valid graph on transient failure."""
    async with _cache_lock:
        now = time.monotonic()
        if _topology_cache.topology is not None and (now - _topology_cache.cached_at) < _CACHE_TTL_SEC:
            return _topology_cache.topology

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.get(
                    HOMELAB_TOPOLOGY_URL,
                    headers={"User-Agent": "nabla-homelab-topology/1.0"},
                )
                response.raise_for_status()
                topology = HomelabTopology.model_validate(response.json())
        except Exception as exc:
            _log.warning(
                "Homelab topology fetch/validation failed (%s): %s",
                HOMELAB_TOPOLOGY_URL,
                exc,
            )
            if _topology_cache.topology is not None:
                return _topology_cache.topology
            return HomelabTopology()

        _topology_cache.topology = topology
        _topology_cache.cached_at = time.monotonic()
        return topology
