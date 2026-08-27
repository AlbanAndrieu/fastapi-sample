"""pfSense-specific exposure probes used by the ``/sickz`` endpoint."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx

PFSENSE_EXTRA_TCP_PORTS: tuple[int, ...] = (
    22,
    9922,
    8076,
    7000,
    8200,
    9000,
    3000,
    4000,
    10443,
    1194,
    1195,
    8080,
    8081,
    8091,
)

_PFSENSE_TCP_PORT_POLICY: dict[int, dict[str, Any]] = {
    22: {
        "service": "SSH",
        "expected_reachable": False,
        "probe": "ssh",
        "reason": "Remote shell access must not be exposed to the public Internet.",
    },
    9922: {
        "service": "TrueNAS SSH",
        "expected_reachable": False,
        "probe": "ssh",
        "reason": (
            "TrueNAS SSH may be enabled for trusted LAN administration but must not "
            "be exposed to the public Internet."
        ),
    },
    4000: {
        "service": "LiteLLM",
        "expected_reachable": False,
        "probe": "http",
        "reason": "LiteLLM should only be exposed through the approved reverse proxy/tunnel path.",
    },
    7000: {
        "service": "TrueNAS via pfSense HAProxy",
        "expected_reachable": True,
        "probe": "https",
        "reason": (
            "pfSense HAProxy intentionally publishes TrueNAS HTTPS/API on WAN port "
            "7000 and re-encrypts traffic to 172.17.0.24:7000. This is direct HAProxy "
            "exposure, not a Cloudflare Tunnel."
        ),
    },
    10443: {
        "service": "pfSense Admin UI",
        "expected_reachable": False,
        "probe": "https",
        "reason": (
            "pfSense administration may be reachable from the trusted LAN/VPN, but "
            "WAN port 10443 must not be reachable from an external runtime such as "
            "FastAPI Cloud."
        ),
    },
}

_KNOWN_PAAS_ENV_MARKERS: tuple[str, ...] = (
    "VERCEL",
    "AWS_EXECUTION_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "KUBERNETES_SERVICE_HOST",
    "FLY_APP_NAME",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PROJECT_ID",
    "HEROKU_APP_NAME",
    "DYNO",
)


def pfsense_tcp_port_policy_payload() -> dict[str, dict[str, Any]]:
    return {
        str(port): dict(policy)
        for port, policy in _PFSENSE_TCP_PORT_POLICY.items()
    }


def pfsense_canonical_href(urls: list[str]) -> str | None:
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


def pfsense_canonical_tcp_host(urls: list[str]) -> str | None:
    href = pfsense_canonical_href(urls)
    if not href:
        return None
    host = (urlparse(href).hostname or "").strip().lower()
    return host or None


def canonical_pfsense_alias_urls(default_targets: str) -> list[str]:
    first_segment = default_targets.replace("\n", ",").split(",")[0].strip()
    aliases = [
        alias.strip()
        for alias in first_segment.split("|")
        if alias.strip()
    ]
    if aliases and pfsense_canonical_href(aliases) is not None:
        return aliases
    return [
        "https://home.albandrieu.com:10443/",
        "https://172.17.0.1:10443/",
        "http://172.17.0.1:8076/",
    ]


def groups_include_pfsense(groups: list[list[str]]) -> bool:
    return any(pfsense_canonical_href(group) is not None for group in groups)


def ensure_pfsense_group(
    groups: list[list[str]],
    *,
    default_targets: str,
) -> list[list[str]]:
    """Always keep a pfSense row for ``/sickz`` and the API board."""
    if groups_include_pfsense(groups):
        return groups
    return [canonical_pfsense_alias_urls(default_targets), *groups]


def pfsense_tcp_skip_payload(urls: list[str]) -> dict[str, Any]:
    if not pfsense_canonical_tcp_host(urls):
        return {}
    return {
        "pfsense_tcp_ports": {
            str(port): None for port in PFSENSE_EXTRA_TCP_PORTS
        },
        "pfsense_tcp_port_policy": pfsense_tcp_port_policy_payload(),
        "pfsense_tcp_ports_skipped": True,
    }


def known_paas_runtime_detected() -> bool:
    env = os.environ
    return any(
        env.get(key) is not None and str(env.get(key)).strip() != ""
        for key in _KNOWN_PAAS_ENV_MARKERS
    )


async def _probe_tcp_port_open(
    host: str,
    port: int,
    *,
    timeout_s: float = 2.0,
) -> bool:
    """Raw TCP probe, only where PaaS interception cannot mislead us."""
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


async def _probe_ssh_port(
    host: str,
    port: int,
    *,
    timeout_s: float = 2.0,
) -> bool | None:
    """Require an SSH banner instead of trusting a TCP handshake alone."""
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
        banner = await asyncio.wait_for(reader.read(128), timeout=timeout_s)
    except (TimeoutError, OSError, ConnectionError):
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
    if banner.startswith(b"SSH-"):
        return True
    return None


async def _probe_http_port(
    host: str,
    port: int,
    *,
    secure: bool,
    timeout_s: float = 3.0,
) -> bool:
    """Require HTTP(S) so cloud TCP interception is not a false positive."""
    scheme = "https" if secure else "http"
    url = f"{scheme}://{host}:{port}/"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            verify=False,
            follow_redirects=False,
        ) as client:
            await client.get(
                url,
                headers={"User-Agent": "nabla-sickz-port-probe/1.0"},
            )
    except (httpx.HTTPError, OSError):
        return False
    return True


async def probe_pfsense_tcp_port(host: str, port: int) -> bool | None:
    """Probe known services by protocol; avoid bare-TCP PaaS false positives."""
    policy = _PFSENSE_TCP_PORT_POLICY.get(port)
    probe = policy.get("probe") if policy else None
    if probe == "ssh":
        return await _probe_ssh_port(host, port)
    if probe == "http":
        return await _probe_http_port(host, port, secure=False)
    if probe == "https":
        return await _probe_http_port(host, port, secure=True)
    if known_paas_runtime_detected():
        return None
    return await _probe_tcp_port_open(host, port)
