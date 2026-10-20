"""Additional, fail-closed source-IP restriction for human owner endpoints.

A trusted home IP is never a replacement for signed Cloudflare Access identity.
Only the ASGI client address is considered; request headers are untrusted.
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Any

type IPNetwork = IPv4Network | IPv6Network


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


def allowed_owner_source(scope: dict[str, Any], settings: Any) -> bool:
    """Check the ASGI client, not spoofable CF-Connecting-IP/XFF headers."""
    raw = getattr(settings, "homelab_trusted_cidrs", "")
    if not isinstance(raw, str) or not raw.strip():
        return False
    # RFC1918/loopback proxy peers may supply a client IP only when explicitly
    # allowlisted and the edge OVERWRITES forwarded headers (not appends).
    # Never use FORWARDED_ALLOW_IPS=* or trust a caller-controlled IP header.
    peer = scope.get("client")
    if not isinstance(peer, (tuple, list)) or not peer or not isinstance(peer[0], str):
        return False
    try:
        peer_ip = ip_address(peer[0])
        hdrs = scope.get("headers", [])
        if not isinstance(hdrs, (list, tuple)):
            return False
        # Duplicate XFF headers cannot be collapsed safely: reject outright.
        sensitive_headers = {
            "x-forwarded-for",
            "cf-connecting-ip",
            "forwarded",
            "x-real-ip",
        }
        addresses: dict[str, str] = {}
        for header in hdrs:
            if not isinstance(header, (tuple, list)) or len(header) != 2:
                return False
            key, value = header
            if not isinstance(key, bytes) or not isinstance(value, bytes):
                return False
            name = key.decode("latin-1").lower()
            if name in sensitive_headers and name in addresses:
                return False
            if name in sensitive_headers:
                addresses[name] = value.decode("latin-1").strip()
        # Reject ambiguous forwarded source chains or multiple header authorities.
        xff = addresses.get("x-forwarded-for")
        cf = addresses.get("cf-connecting-ip")
        if addresses.get("forwarded") or addresses.get("x-real-ip"):
            return False
        if xff or cf:
            proxies = getattr(settings, "homelab_trusted_proxy_cidrs", "")
            if not proxies or not any(peer_ip in network for network in parse_cidrs(proxies)):
                return False
            if not xff or "," in xff or (cf and cf != xff):
                return False
            source = ip_address(xff)
        else:
            source = peer_ip
        return any(source in cidr for cidr in parse_cidrs(raw))
    except (TypeError, ValueError):
        # Invalid configuration, malformed headers or unknown peer fail closed.
        return False
