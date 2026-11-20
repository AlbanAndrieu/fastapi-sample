"""IPv6 negative-exposure probes for ``/sickz``.

Without NAT, every homelab host behind the R7000 has a public ``2a01:e0a:a17:3c01::/64``
address. Only the Freebox IPv6 firewall (and ufw on the workstation) keep it closed, so this
runtime, outside the LAN, checks that the HTTP services stay unreachable.
"""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
from typing import Any

import httpx

# HTTP-speaking listeners only: a bare TCP handshake can be faked by PaaS egress proxies.
IPV6_EXPOSURE_HTTP_PORTS: tuple[int, ...] = (80, 443, 3100, 8087, 9090, 11434)
# AAAA-only name: it answers only when this runtime really has IPv6 egress.
_IPV6_EGRESS_URL = "https://ipv6.google.com/"


def parse_ipv6_targets(raw: str) -> dict[str, str]:
    """Parse ``label=address`` pairs; keep only global IPv6 addresses (trust boundary)."""
    targets: dict[str, str] = {}
    for item in raw.replace("\n", ",").split(","):
        label, sep, address = item.strip().partition("=")
        if not sep:
            continue
        try:
            parsed = ipaddress.IPv6Address(address.strip())
        except ValueError:
            continue
        if parsed.is_global:
            targets[label.strip()] = str(parsed)
    return targets


async def _ipv6_egress_available(timeout_s: float = 3.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            await client.head(_IPV6_EGRESS_URL)
    except (httpx.HTTPError, OSError):
        return False
    return True


async def _http_answers(address: str, port: int, timeout_s: float = 3.0) -> bool:
    """Any HTTP answer means exposed. A certificate error too: a TLS server answered."""
    scheme = "https" if port == 443 else "http"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), follow_redirects=False) as client:
            await client.get(f"{scheme}://[{address}]:{port}/", headers={"User-Agent": "nabla-sickz-ipv6-probe/1.0"})
    except httpx.ConnectError as exc:
        # An IP literal never matches a certificate: the handshake itself proves a listener.
        return isinstance(exc.__context__, ssl.SSLError)
    except (httpx.HTTPError, OSError):
        return False
    return True


async def probe_ipv6_exposure(raw_targets: str) -> dict[str, Any]:
    targets = parse_ipv6_targets(raw_targets)
    if not targets:
        return {"status": "not_configured", "detail": "SICKZ_IPV6_TARGETS has no global IPv6 label=address pair."}
    if not await _ipv6_egress_available():
        # A refused or dropped probe would prove nothing without IPv6 egress.
        return {"status": "unknown", "egress_ipv6": False, "detail": "This runtime has no IPv6 egress."}

    labels = list(targets)
    results = await asyncio.gather(
        *(_http_answers(targets[label], port) for label in labels for port in IPV6_EXPOSURE_HTTP_PORTS),
    )
    reachable = iter(results)
    ports = {label: {str(port): next(reachable) for port in IPV6_EXPOSURE_HTTP_PORTS} for label in labels}
    exposed = any(open_ for by_port in ports.values() for open_ in by_port.values())
    return {
        "status": "exposed" if exposed else "not_exposed",
        "egress_ipv6": True,
        "expected_reachable": False,
        "ports": ports,
    }
