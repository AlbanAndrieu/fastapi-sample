"""Typed declared homelab topology sourced from nabla-compose."""

from __future__ import annotations

import asyncio
from enum import StrEnum
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Literal

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from nabla.api.site_architecture_catalog import fetch_catalog_v2_source, load_catalog_snapshot

HOMELAB_TOPOLOGY_URL = "https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/operator-inventory.json"
HOMELAB_TOPOLOGY_SNAPSHOT_PATH = Path(__file__).with_name("data") / "operator-inventory.json"
_CACHE_TTL_SEC = 300.0
_FETCH_TIMEOUT_SEC = 4.0
_log = logging.getLogger(__name__)
_cache_lock = asyncio.Lock()


class HomelabRelationType(StrEnum):
    """Supported design-time relationships between homelab components."""

    DEPENDS_ON = "dependsOn"
    CONSUMES_API = "consumesApi"
    PROVIDES_API = "providesApi"
    PART_OF = "partOf"
    HOSTED_BY = "hostedBy"
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


class HomelabTopologyEnvironment(BaseModel):
    """Named deployment environment attached to a logical topology node."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    name: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    external: bool
    cloudflare_tunnel: bool = Field(
        validation_alias=AliasChoices("cloudflareTunnel", "cloudflare_tunnel"),
        serialization_alias="cloudflareTunnel",
    )


class HomelabTopologyRuntime(BaseModel):
    """Runtime ownership metadata exported by the canonical service catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    provider: Literal["truenas-app", "truenas-vm", "logical", "external", "host"]
    app_id: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("appId", "app_id"),
        serialization_alias="appId",
    )
    container_service: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("containerService", "container_service"),
        serialization_alias="containerService",
    )
    networks: list[str] | None = Field(default=None, min_length=1)
    instances: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_unique_networks(self) -> HomelabTopologyRuntime:
        """A runtime network is an identity set, not an ordered duplicate list."""
        if self.networks is not None and len(self.networks) != len(set(self.networks)):
            raise ValueError("runtime.networks must not contain duplicates")
        if self.instances is not None and len(self.instances) != len(set(self.instances)):
            raise ValueError("runtime.instances must not contain duplicates")
        return self


class HomelabTopologyLifecycle(BaseModel):
    """Declarative TrueNAS lifecycle phase and priority from nabla-compose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: Literal[
        "bootstrap-runtime",
        "foundation",
        "network-edge",
        "primary-data",
        "secondary-data",
        "platform-services",
        "applications",
    ]
    priority: int = Field(ge=0, le=1000)
    blocks_later_waves: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("blocksLaterWaves", "blocks_later_waves"),
        serialization_alias="blocksLaterWaves",
    )


class HomelabTopologyMonitoring(BaseModel):
    """Declared service protocol/health capability exported by nabla-compose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["http", "port", "provider"]
    target: str | None = Field(default=None, min_length=1, max_length=2048)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    host: str | None = Field(default=None, min_length=1, max_length=512)
    port: int | None = Field(default=None, ge=1, le=65535)
    conditions: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_probe_target(self) -> HomelabTopologyMonitoring:
        """Monitoring metadata must identify the declared protocol endpoint."""
        if self.target or self.url or (self.host and self.port):
            return self
        raise ValueError("monitoring requires target/url or host+port")


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
    presentation_role: Literal["service", "core", "support"] | None = Field(
        default=None,
        validation_alias=AliasChoices("presentationRole", "presentation_role"),
        serialization_alias="presentationRole",
    )
    criticality: Literal["critical", "high", "medium", "low"] | None = None
    status: Literal["active", "planned", "disabled"] | None = None
    security_functions: list[Literal["govern", "identify", "protect", "detect", "respond", "recover"]] | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("securityFunctions", "security_functions"),
        serialization_alias="securityFunctions",
    )
    source_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        validation_alias=AliasChoices("sourcePath", "source_path"),
        serialization_alias="sourcePath",
    )
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    internal_url: str | None = Field(
        default=None,
        min_length=1,
        max_length=2048,
        validation_alias=AliasChoices("internalUrl", "internal_url"),
        serialization_alias="internalUrl",
    )
    description: str | None = Field(default=None, max_length=1024)
    icon: str | None = Field(default=None, min_length=1, max_length=32)
    environments: list[HomelabTopologyEnvironment] | None = Field(
        default=None,
        min_length=1,
    )
    runtime: HomelabTopologyRuntime | None = None
    lifecycle: HomelabTopologyLifecycle | None = None
    monitoring: HomelabTopologyMonitoring | None = None

    @model_validator(mode="after")
    def require_unique_security_functions(self) -> HomelabTopologyNode:
        """Reject ambiguous duplicate NIST CSF function metadata."""
        if self.security_functions is not None and len(self.security_functions) != len(
            set(self.security_functions),
        ):
            raise ValueError("securityFunctions must not contain duplicates")
        if self.environments is not None:
            names = [environment.name for environment in self.environments]
            if len(names) != len(set(names)):
                raise ValueError("environments must not contain duplicate names")
        return self


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
    catalog_revision: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$", alias="catalogRevision")
    operator_revision: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$", alias="operatorRevision")
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


def _add_public_node_descriptors(item: dict[str, object], node: HomelabTopologyNode) -> None:
    """Copy optional presentation descriptors in their stable public order."""
    if node.presentation_role is not None:
        item["presentationRole"] = node.presentation_role
    if node.criticality is not None:
        item["criticality"] = node.criticality
    if node.status is not None:
        item["status"] = node.status
    if node.security_functions is not None:
        item["securityFunctions"] = list(node.security_functions)
    if node.description is not None:
        item["description"] = node.description
    if node.icon is not None:
        item["icon"] = node.icon


def _public_topology_node(node: HomelabTopologyNode) -> dict[str, object]:
    """Return one browser-safe node without privileged endpoint evidence."""
    item: dict[str, object] = {
        "id": node.id,
        "name": node.name,
        "kind": node.kind,
        "category": node.category,
    }
    _add_public_node_descriptors(item, node)
    if node.environments is not None:
        item["environments"] = [{"name": environment.name} for environment in node.environments]
    if node.lifecycle is not None:
        item["lifecycle"] = node.lifecycle.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    if node.runtime is not None:
        item["runtime"] = {"provider": node.runtime.provider}
    return item


def public_topology_payload(topology: HomelabTopology) -> dict[str, object]:
    """Return a browser-safe declared graph without privileged endpoint evidence."""
    nodes = [_public_topology_node(node) for node in topology.nodes]

    relations = [
        {
            "source": relation.source,
            "target": relation.target,
            "type": relation.type.value,
            "strength": relation.strength.value,
            **({"description": relation.description} if relation.description is not None else {}),
        }
        for relation in topology.relations
    ]
    return {
        "version": topology.version,
        **({"catalogRevision": topology.catalog_revision} if topology.catalog_revision else {}),
        **({"operatorRevision": topology.operator_revision} if topology.operator_revision else {}),
        "name": topology.name,
        "projection": "public-sanitized",
        "nodes": nodes,
        "relations": relations,
    }


def project_operator_inventory(raw: dict[str, Any], catalog: dict[str, Any]) -> HomelabTopology:
    """Verify canonical revision, native graph integrity and explicit Compose bindings."""
    if raw.get("schemaVersion") != 2 or raw.get("model") != "backstage-operator-inventory":
        raise ValueError("operator graph requires v2 inventory")
    if raw.get("catalogRevision") != catalog.get("catalogRevision"):
        raise ValueError("operator graph catalog revision mismatch")
    material = {key: raw[key] for key in ("services", "nodes", "relations")}
    digest = hashlib.sha256(json.dumps(material, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    if raw.get("operatorRevision") != "sha256:" + digest:
        raise ValueError("operator graph content revision mismatch")
    refs = {entity["entityRef"] for entity in catalog["entities"]}
    bindings = raw["identityBindings"]
    ids = {row["id"] for row in raw["services"]}
    if set(bindings) != ids or not set(bindings.values()) <= refs:
        raise ValueError("operator graph identity crosswalk mismatch")
    if set(raw["operationalOnlyNodeIds"]) != {node["id"] for node in raw["nodes"]} - ids:
        raise ValueError("operator-only node classification mismatch")
    return HomelabTopology.model_validate(raw)


def _load_packaged_topology() -> HomelabTopology:
    """Load the packaged canonical topology snapshot for cold-start fallback."""
    try:
        payload = json.loads(HOMELAB_TOPOLOGY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        topology = project_operator_inventory(payload, load_catalog_snapshot())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _log.error(
            "Packaged homelab topology load/validation failed (%s): %s",
            HOMELAB_TOPOLOGY_SNAPSHOT_PATH,
            exc,
        )
        return HomelabTopology()
    return topology


class _TopologyCache:
    """Last-known-good topology plus monotonic cache timestamp."""

    __slots__ = ("cached_at", "refresh_task", "topology")

    def __init__(self) -> None:
        self.topology: HomelabTopology | None = None
        self.cached_at = 0.0
        self.refresh_task: asyncio.Task[HomelabTopology] | None = None


_topology_cache = _TopologyCache()


async def _fetch_homelab_topology_origin() -> HomelabTopology:
    catalog = await fetch_catalog_v2_source()
    async with httpx.AsyncClient(timeout=httpx.Timeout(_FETCH_TIMEOUT_SEC), follow_redirects=False, trust_env=False) as client:
        response = await client.get(
            HOMELAB_TOPOLOGY_URL,
            headers={"User-Agent": "nabla-homelab-topology/1.0"},
        )
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ValueError("operator inventory exceeds size budget")
        return project_operator_inventory(response.json(), catalog)


async def _refresh_homelab_topology() -> HomelabTopology:
    """Refresh the remote topology while retaining the last known good graph."""
    try:
        topology = await _fetch_homelab_topology_origin()
        _log.info(
            "Homelab topology origin validated nodes=%d relations=%d",
            len(topology.nodes),
            len(topology.relations),
        )
    except Exception as exc:
        _log.warning(
            "Homelab topology fetch/validation failed (%s): %s",
            HOMELAB_TOPOLOGY_URL,
            exc,
        )
        async with _cache_lock:
            if _topology_cache.topology is not None:
                return _topology_cache.topology
            packaged = _load_packaged_topology()
            _log.warning(
                "Homelab topology cold-start fallback selected nodes=%d relations=%d",
                len(packaged.nodes),
                len(packaged.relations),
            )
            return packaged

    async with _cache_lock:
        _topology_cache.topology = topology
        _topology_cache.cached_at = time.monotonic()
    return topology


async def fetch_homelab_topology() -> HomelabTopology:
    """Serve cached topology immediately and refresh expired data in background."""
    async with _cache_lock:
        now = time.monotonic()
        if _topology_cache.topology is not None and (now - _topology_cache.cached_at) < _CACHE_TTL_SEC:
            return _topology_cache.topology

        if _topology_cache.refresh_task is None or _topology_cache.refresh_task.done():
            _topology_cache.refresh_task = asyncio.create_task(
                _refresh_homelab_topology(),
                name="homelab-topology-refresh",
            )
        refresh_task = _topology_cache.refresh_task
        stale_topology = _topology_cache.topology

    if stale_topology is not None:
        return stale_topology
    return await asyncio.shield(refresh_task)
