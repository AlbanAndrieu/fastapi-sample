"""Bounded DNS preflight evidence for public service probes."""

from __future__ import annotations

import socket
import time
from typing import Any

import dns.asyncresolver
import dns.exception

_DNS_PROBE_TIMEOUT_SEC = 1.5
_RESOLVER_LABELS = {
    "127.0.0.11": "Docker embedded DNS",
    "1.1.1.1": "Cloudflare DNS",
    "1.0.0.1": "Cloudflare DNS",
    "9.9.9.9": "Quad9",
    "149.112.112.112": "Quad9",
    "8.8.8.8": "Google Public DNS",
    "8.8.4.4": "Google Public DNS",
}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _short_error(exc: BaseException) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:240]


def _resolver_display(address: str) -> str:
    label = _RESOLVER_LABELS.get(address)
    return f"{address} ({label})" if label else address


def _resolver() -> dns.asyncresolver.Resolver:
    """Create an async resolver from the runtime system resolver configuration."""
    return dns.asyncresolver.Resolver(configure=True)


def system_dns_resolvers(
    resolver: dns.asyncresolver.Resolver | None = None,
) -> tuple[str, ...]:
    """Return bounded resolver identities without parsing resolv.conf ourselves."""
    selected = resolver or _resolver()
    addresses: list[str] = []
    for nameserver in selected.nameservers:
        address = getattr(nameserver, "address", nameserver)
        value = str(address).strip()
        if value and value not in addresses:
            addresses.append(value)
    return tuple(_resolver_display(address) for address in addresses[:4])


async def probe_dns_hostname(
    hostname: str,
    *,
    timeout_seconds: float = _DNS_PROBE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Resolve public A/AAAA evidence asynchronously with dnspython."""
    started = time.perf_counter()
    resolver = _resolver()
    base: dict[str, Any] = {
        "dns_hostname": hostname,
        "dns_probe": "dnspython.resolve_name",
        "dns_resolver_source": "system",
        "dns_resolvers": list(system_dns_resolvers(resolver)),
    }
    try:
        answers = await resolver.resolve_name(
            hostname,
            family=socket.AF_UNSPEC,
            lifetime=timeout_seconds,
            raise_on_no_answer=False,
        )
        addresses = sorted(set(answers.addresses()))
        if not addresses:
            raise dns.resolver.NoAnswer
    except (dns.exception.DNSException, OSError, TimeoutError) as exc:
        return {
            **base,
            "dns_state": "fail",
            "dns_latency_ms": _elapsed_ms(started),
            "dns_error": _short_error(exc),
            "dns_resolved": [],
        }

    return {
        **base,
        "dns_state": "ok",
        "dns_latency_ms": _elapsed_ms(started),
        "dns_resolved": addresses[:4],
    }
