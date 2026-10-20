"""Additional, fail-closed source-IP restriction for human owner endpoints.

A trusted home IP is never a replacement for signed Cloudflare Access identity.
Only the ASGI client address is considered; request headers are untrusted.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from typing import Any

type IPNetwork = IPv4Network | IPv6Network
type IPAddress = IPv4Address | IPv6Address


def parse_cidrs(raw: str) -> tuple[IPNetwork, ...]:
    """Validate strict, bounded comma-separated CIDRs; reject allow-all entries."""
    entries = [part.strip() for part in raw.split(",")]
    if not 1 <= len(entries) <= 32 or any(not entry for entry in entries):
        raise ValueError("invalid HOMELAB_TRUSTED_CIDRS list")
    networks: list[IPNetwork] = []
    for entry in entries:
        network = ip_network(entry, strict=True)
        if network.prefixlen == 0:
            raise ValueError("HOMELAB_TRUSTED_CIDRS cannot allow every address")
        networks.append(network)
    return tuple(networks)


def _sensitive_headers(raw: object) -> dict[str, str] | None:
    """Reject malformed or duplicate ASGI provenance fields before IP checks."""
    if not isinstance(raw, (list, tuple)):
        return None

    names = {"x-forwarded-for", "cf-connecting-ip", "forwarded", "x-real-ip"}
    values: dict[str, str] = {}
    for header in raw:
        if not isinstance(header, (tuple, list)) or len(header) != 2:
            return None
        key, value = header
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            return None
        name = key.decode("latin-1").lower()
        if name in names:
            if name in values:
                return None
            values[name] = value.decode("latin-1").strip()
    return values


def _source_from_headers(
    addresses: dict[str, str], peer: IPAddress, settings: Any
) -> IPAddress | None:
    """Honor a single overwritten XFF only from a configured proxy peer."""
    if addresses.get("forwarded") or addresses.get("x-real-ip"):
        return None

    xff = addresses.get("x-forwarded-for")
    cf = addresses.get("cf-connecting-ip")
    if not (xff or cf):
        return peer
    if not xff or "," in xff or (cf and cf != xff):
        return None

    raw_proxies = getattr(settings, "homelab_trusted_proxy_cidrs", "")
    if not isinstance(raw_proxies, str) or not raw_proxies.strip():
        return None
    if not any(peer in net for net in parse_cidrs(raw_proxies)):
        return None
    return ip_address(xff)


def allowed_owner_source(scope: dict[str, Any], settings: Any) -> bool:
    """Allow signed owner sessions only from an approved, unspoofed IP."""
    raw = getattr(settings, "homelab_trusted_cidrs", "")
    if not isinstance(raw, str) or not raw.strip():
        return False

    peer = scope.get("client")
    if not isinstance(peer, (tuple, list)) or not peer or not isinstance(peer[0], str):
        return False

    try:
        peer_ip = ip_address(peer[0])
        headers = _sensitive_headers(scope.get("headers", []))
        if headers is None:
            return False
        source = _source_from_headers(headers, peer_ip, settings)
        return source is not None and any(source in net for net in parse_cidrs(raw))
    except (TypeError, ValueError):
        return False
