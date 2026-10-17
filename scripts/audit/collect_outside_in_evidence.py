#!/usr/bin/env python3
"""Collect sanitized public DNS and outside-in HTTP evidence for exposure audits.

Read-only: one DNS resolution and one HTTP GET (no redirect following, no
credentials) per declared hostname. The output feeds
``garage_exposure_drift.py --observed``. Cloudflare Tunnel, pfSense and Traefik
layers are never inferred here; they stay ``unknown`` until collected from
their own read-only configuration sources.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

Resolver = Callable[[str], list[str]]
ACCESS_LOGIN_SUFFIX = ".cloudflareaccess.com"


def system_resolver(hostname: str) -> list[str]:
    """Resolve with the operator's system resolver; the vantage point is recorded."""
    infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def _is_public(address: str) -> bool:
    return ipaddress.ip_address(address).is_global


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dns_layer(hostname: str, *, external: bool, resolver: Resolver) -> tuple[dict[str, Any], list[str]]:
    """A private service with a public record is visible, not proven drift."""
    observed_at = _now()
    try:
        addresses = resolver(hostname)
    except socket.gaierror:
        status = "drift" if external else "matched"
        return {"status": status, "source": "dns_lookup", "observed_at": observed_at}, []
    public = [address for address in addresses if _is_public(address)]
    if not public:
        # LAN-only resolution says nothing about public DNS.
        return {"status": "unknown"}, addresses
    status = "matched" if external else "observed"
    return {"status": status, "source": "dns_lookup", "observed_at": observed_at}, addresses


def _http_layers(url: str, client: httpx.Client) -> dict[str, dict[str, Any]]:
    """Classify one anonymous GET; an Access redirect is edge evidence only."""
    observed_at = _now()
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return {}
    record = {"source": "outside_in", "observed_at": observed_at, "http_status": response.status_code}
    location = urlsplit(response.headers.get("location", ""))
    if response.is_redirect and (location.hostname or "").endswith(ACCESS_LOGIN_SUFFIX):
        return {"cloudflare_access": {"status": "observed", **record}}
    if response.status_code == 403 and response.headers.get("cf-mitigated") == "challenge":
        return {"cloudflare_access": {"status": "observed", **record}}
    return {"outside_in_origin": {"status": "observed", **record}}


def collect(
    services: list[dict[str, Any]],
    *,
    resolver: Resolver = system_resolver,
    client: httpx.Client | None = None,
    hairpin_addresses: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return ``{"observations": [...]}`` for services with a declared hostname.

    ``hairpin_addresses`` lists the operator's own WAN addresses: from inside
    the LAN, a request to them loops through NAT reflection and is not
    outside-in evidence, so HTTP is skipped for hostnames resolving only there.
    """
    owned_client = client is None
    http = client or httpx.Client(timeout=5.0, follow_redirects=False)
    observations = []
    try:
        for service in services:
            url = service.get("tunnelUrl")
            hostname = urlsplit(url).hostname if isinstance(url, str) else None
            if not hostname:
                continue
            external = service.get("external") is True
            dns, addresses = _dns_layer(hostname, external=external, resolver=resolver)
            layers: dict[str, dict[str, Any]] = {"public_dns": dns}
            # Only a request leaving the LAN is outside-in; LAN or hairpin answers are not.
            if any(_is_public(address) and address not in hairpin_addresses for address in addresses):
                layers.update(_http_layers(f"https://{hostname}/", http))
            observations.append({"service_id": service["id"], "layers": layers})
    finally:
        if owned_client:
            http.close()
    return {"observations": observations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="homelab-services.json")
    parser.add_argument("--ids", required=True, help="comma-separated service ids")
    parser.add_argument("--declared-output", type=Path, required=True)
    parser.add_argument("--observed-output", type=Path, required=True)
    parser.add_argument(
        "--hairpin-address",
        action="append",
        default=[],
        help="own WAN address reached by NAT reflection from the LAN (repeatable)",
    )
    args = parser.parse_args()
    wanted = [item.strip() for item in args.ids.split(",") if item.strip()]
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    by_id = {row.get("id"): row for row in catalog.get("services", []) if isinstance(row, dict)}
    missing = [service_id for service_id in wanted if service_id not in by_id]
    if missing:
        parser.error(f"unknown service ids: {', '.join(missing)}")
    services = [by_id[service_id] for service_id in wanted]
    declared = {
        "catalog_revision": str(catalog.get("revision") or "unknown"),
        "services": [{"id": row["id"], "external": row.get("external") is True} for row in services],
    }
    args.declared_output.write_text(json.dumps(declared, indent=2) + "\n", encoding="utf-8")
    observed = collect(services, hairpin_addresses=frozenset(args.hairpin_address))
    args.observed_output.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
