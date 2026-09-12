"""Bounded DNS preflight evidence for homelab service probes."""

from __future__ import annotations

import asyncio
import socket
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

_DNS_PROBE_TIMEOUT_SEC = 1.5
_RESOLV_CONF = Path("/etc/resolv.conf")
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


def _parse_resolv_conf(text: str) -> tuple[str, ...]:
    """Extract unique nameserver addresses from resolv.conf text."""
    resolvers: list[str] = []
    for line in text.splitlines():
        value = line.split("#", 1)[0].strip()
        if not value.startswith("nameserver "):
            continue
        parts = value.split()
        if len(parts) < 2:
            continue
        address = parts[1].strip()
        if address and address not in resolvers:
            resolvers.append(address)
    return tuple(resolvers[:4])


def _resolver_display(address: str) -> str:
    label = _RESOLVER_LABELS.get(address)
    return f"{address} ({label})" if label else address


@lru_cache(maxsize=1)
def system_dns_resolvers() -> tuple[str, ...]:
    """Return the runtime nameservers without exposing unrelated resolver config."""
    try:
        text = _RESOLV_CONF.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple(_resolver_display(address) for address in _parse_resolv_conf(text))


async def probe_dns_hostname(
    hostname: str,
    *,
    timeout_seconds: float = _DNS_PROBE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Resolve one hostname through the runtime system resolver with a strict timeout."""
    started = time.perf_counter()
    base: dict[str, Any] = {
        "dns_hostname": hostname,
        "dns_probe": "getaddrinfo",
        "dns_resolver_source": "/etc/resolv.conf",
        "dns_resolvers": list(system_dns_resolvers()),
    }
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                None,
                type=socket.SOCK_STREAM,
            ),
            timeout=timeout_seconds,
        )
    except (OSError, TimeoutError) as exc:
        return {
            **base,
            "dns_state": "fail",
            "dns_latency_ms": _elapsed_ms(started),
            "dns_error": _short_error(exc),
            "dns_resolved": [],
        }

    addresses = sorted({str(item[4][0]) for item in results if item and item[4]})
    return {
        **base,
        "dns_state": "ok",
        "dns_latency_ms": _elapsed_ms(started),
        "dns_resolved": addresses[:4],
    }
