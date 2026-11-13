"""Backstage v2 fixtures: tests declare ``x-nabla`` routes, never flat service rows."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from nabla.api.catalog_routes import (
    CLOUDFLARE_TUNNEL_GATEWAY,
    DIRECT_WAN_GATEWAY,
    CatalogRoute,
    routes_from_catalog,
)

_EDGES = {"cloudflare": CLOUDFLARE_TUNNEL_GATEWAY, "direct": DIRECT_WAN_GATEWAY, None: "resource:default/truenas"}


def route(
    url: str | None = None,
    *,
    public: bool = False,
    edge: str | None = "cloudflare",
    access: bool | None = None,
    backend: tuple[Any, ...] | None = None,
    probe_path: str | None = None,
    risk: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """One ``x-nabla.exposure`` item; ``edge`` picks the public gatewayRef."""
    item: dict[str, Any] = {
        "name": name or ("public" if public else "lan"),
        "visibility": "public" if public else "lan",
        "protocol": "HTTPS",
        "gatewayRef": _EDGES[edge] if public else "resource:default/truenas",
    }
    if url:
        parsed = urlsplit(url)
        item["hostnames"] = [parsed.hostname]
        if parsed.port:
            item["port"] = parsed.port
    if public:
        item["access"] = {"required": edge == "cloudflare" if access is None else access}
    if backend:
        host, port, *tls = backend
        item["backend"] = {"host": host, "port": port, **({"appProtocol": "https"} if tls and tls[0] else {})}
    if probe_path:
        item["probePath"] = probe_path
    if risk:
        item["riskAcceptance"] = {"id": "test-risk", "status": "accepted", "reason": risk}
    return item


def entity(
    name: str,
    *routes: dict[str, Any],
    kind: str = "Component",
    title: str | None = None,
    rank: int | None = None,
    position: int = 0,
) -> dict[str, Any]:
    """A Backstage entity as generated in nabla-compose entities.json."""
    spec: dict[str, Any] = {"exposure": list(routes)}
    if rank is not None:
        spec["probePolicy"] = {"deploymentUnit": name, "rank": rank, "position": position}
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": kind,
        "entityRef": f"{kind.lower()}:default/{name}",
        "sourcePath": f"apps/{name}/catalog-info.yaml",
        "metadata": {"name": name, "title": title or name},
        "spec": {"type": "service", "lifecycle": "production"},
        **({"x-nabla": spec} if routes else {}),
    }


def catalog(*entities: dict[str, Any]) -> dict[str, Any]:
    """entities.json payload with a valid catalogRevision digest."""
    ordered = sorted(entities, key=lambda item: item["entityRef"])
    digest = hashlib.sha256(
        json.dumps(ordered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
    ).hexdigest()
    return {"schemaVersion": 2, "model": "backstage", "catalogRevision": f"sha256:{digest}", "entities": ordered}


def routes(*entities: dict[str, Any]) -> list[CatalogRoute]:
    return list(routes_from_catalog({"entities": list(entities)}))


def service(
    name: str,
    url: str | None = None,
    *,
    title: str | None = None,
    kind: str = "Component",
    rank: int | None = None,
    position: int = 0,
    **route_options: Any,
) -> CatalogRoute:
    """Single-route entity projected through the production route projection."""
    return routes(entity(name, route(url, **route_options), kind=kind, title=title, rank=rank, position=position))[0]
