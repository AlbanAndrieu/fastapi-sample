"""pfSense-specific helpers for inverse-reachability probes."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from nabla.config_settings import _default_sickz_targets_value


_PFSENSE_EXTRA_TCP_PORTS: tuple[int, ...] = (
    22,
    9922,
    8076,
    7000,
    8200,
    9000,
    3000,
    4100,
    1194,
    1195,
    8080,
    8081,
    8091,
)


def _pfsense_canonical_href(urls: list[str]) -> str | None:
    """Return the canonical pfSense UI URL when a group represents pfSense."""
    hosts: set[str] = set()
    for raw in urls:
        parsed = urlparse(raw.strip())
        if parsed.port != 10443:
            continue
        hosts.add((parsed.hostname or "").lower())
    if not hosts:
        return None
    if "home.albandrieu.com" in hosts or "172.17.0.1" in hosts:
        return "https://home.albandrieu.com:10443/"
    return None


def _pfsense_canonical_tcp_host(urls: list[str]) -> str | None:
    href = _pfsense_canonical_href(urls)
    if not href:
        return None
    host = (urlparse(href).hostname or "").strip().lower()
    return host or None


def _canonical_pfsense_alias_urls() -> list[str]:
    raw = _default_sickz_targets_value()
    first_segment = raw.replace("\n", ",").split(",")[0].strip()
    aliases = [alias.strip() for alias in first_segment.split("|") if alias.strip()]
    if aliases and _pfsense_canonical_href(aliases) is not None:
        return aliases
    return [
        "https://home.albandrieu.com:10443/",
        "https://172.17.0.1:10443/",
        "http://172.17.0.1:8076/",
    ]


def _groups_include_pfsense(groups: list[list[str]]) -> bool:
    return any(_pfsense_canonical_href(group) is not None for group in groups)


def _ensure_pfsense_group(groups: list[list[str]]) -> list[list[str]]:
    """Always keep a pfSense row for ``/sickz`` and the API board."""
    if _groups_include_pfsense(groups):
        return groups
    return [_canonical_pfsense_alias_urls(), *groups]


def _pfsense_tcp_skip_payload(urls: list[str]) -> dict[str, Any]:
    if not _pfsense_canonical_tcp_host(urls):
        return {}
    return {
        "pfsense_tcp_ports": {str(port): None for port in _PFSENSE_EXTRA_TCP_PORTS},
        "pfsense_tcp_ports_skipped": True,
    }


async def _probe_tcp_port_open(host: str, port: int, *, timeout_s: float = 2.0) -> bool:
    """Return whether a TCP connection to ``host:port`` succeeds."""
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
    except (TimeoutError, OSError, ConnectionError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True
