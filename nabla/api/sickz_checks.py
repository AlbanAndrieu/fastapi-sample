"""Inverse-reachability probes for the ``/sickz`` endpoint."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import urllib3
from fastapi import Request

from nabla.api.health_probe_utils import (
    normalize_probe_error,
    normalize_probe_result_errors,
    probe_https_tls_trusted,
)
from nabla.api.homelab_catalog import homelab_sickz_catalog_for_sickz
from nabla.config_settings import (
    _ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX,
    APP_DOMAIN,
    APIDeploymentSettings,
    _default_sickz_targets_value,
    get_settings,
)

_log = logging.getLogger(__name__)


def parse_sickz_target_groups(raw: str) -> list[list[str]]:
    """Split SICKZ_TARGETS; ``|`` joins aliases of one logical target."""
    text = (raw or "").replace("\n", ",")
    groups: list[list[str]] = []
    for segment in text.split(","):
        seg = segment.strip()
        if not seg:
            continue
        aliases = [alias.strip() for alias in seg.split("|") if alias.strip()]
        if aliases:
            groups.append(aliases)
    return groups


def _normalize_targets_for_compare(raw: str) -> str:
    parts: list[str] = []
    for segment in (raw or "").replace("\n", ",").split(","):
        value = segment.strip()
        if value:
            parts.append(value)
    return ",".join(parts)


def _targets_equal_default_catalog_mode(raw: str) -> bool:
    """Whether the configured targets still use the pfSense-only default."""
    return _normalize_targets_for_compare(raw) == _normalize_targets_for_compare(
        _default_sickz_targets_value(),
    )


_ALBANDRIEU_COM = f".{_ALBANDRIEU_PUBLIC_DOMAIN_SUFFIX}"
_ICON_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.svg\Z", re.IGNORECASE)


def _validate_icon_filename(name: str) -> str:
    value = name.strip()
    if _ICON_FILENAME_RE.match(value):
        return value
    return "homepage.svg"


def _ipv4_host(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _short_label_for_url(url: str) -> str:
    """Return host/port without scheme and personal-domain suffix."""
    raw = url.strip()
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip().lower()
    port = parsed.port
    if not host:
        tail = re.sub(r"^https?://", "", raw, flags=re.I)
        return (tail[:48] + "…") if len(tail) > 48 else tail
    display = host.removesuffix(_ALBANDRIEU_COM)
    if port and port not in (80, 443):
        return f"{display}:{port}"
    return display


def _display_label(urls: list[str]) -> str:
    if not urls:
        return "target"
    return " · ".join(_short_label_for_url(url) for url in urls)


def _row_href(urls: list[str]) -> str:
    return urls[0].strip() if urls else ""


_PFSENSE_EXTRA_TCP_PORTS: tuple[int, ...] = (
    22,
    9922,
    8076,
    7000,
    8200,
    9000,
    3000,
    4000,
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
    4000: {
        "service": "LiteLLM",
        "expected_reachable": False,
        "probe": "http",
        "reason": "LiteLLM should only be exposed through the approved reverse proxy/tunnel path.",
    },
    7000: {
        "service": "TrueNAS",
        "expected_reachable": True,
        "probe": "https",
        "reason": "TrueNAS is intentionally reachable on this externally published port.",
    },
}


def _pfsense_tcp_port_policy_payload() -> dict[str, dict[str, Any]]:
    return {str(port): dict(policy) for port, policy in _PFSENSE_TCP_PORT_POLICY.items()}


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
    """Always keep a pfSense row for `/sickz` and the API board."""
    if _groups_include_pfsense(groups):
        return groups
    return [_canonical_pfsense_alias_urls(), *groups]


def _pfsense_tcp_skip_payload(urls: list[str]) -> dict[str, Any]:
    if not _pfsense_canonical_tcp_host(urls):
        return {}
    return {
        "pfsense_tcp_ports": {str(port): None for port in _PFSENSE_EXTRA_TCP_PORTS},
        "pfsense_tcp_port_policy": _pfsense_tcp_port_policy_payload(),
        "pfsense_tcp_ports_skipped": True,
    }


async def _probe_tcp_port_open(
    host: str,
    port: int,
    *,
    timeout_s: float = 2.0,
) -> bool:
    """Raw TCP-connect probe, used only where a PaaS interception cannot mislead us."""
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
    """Require an SSH identification banner instead of trusting a TCP handshake alone."""
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
    """Require an HTTP(S) response so cloud egress TCP interception is not a false positive."""
    scheme = "https" if secure else "http"
    url = f"{scheme}://{host}:{port}/"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            verify=False,
            follow_redirects=False,
        ) as client:
            await client.get(url, headers={"User-Agent": "nabla-sickz-port-probe/1.0"})
    except (httpx.HTTPError, OSError):
        return False
    return True


async def _probe_pfsense_tcp_port(host: str, port: int) -> bool | None:
    """Probe known services by protocol; avoid bare-TCP false positives on PaaS."""
    policy = _PFSENSE_TCP_PORT_POLICY.get(port)
    probe = policy.get("probe") if policy else None
    if probe == "ssh":
        return await _probe_ssh_port(host, port)
    if probe == "http":
        return await _probe_http_port(host, port, secure=False)
    if probe == "https":
        return await _probe_http_port(host, port, secure=True)
    if _known_paas_runtime_detected():
        return None
    return await _probe_tcp_port_open(host, port)


def _canonical_https_tunnel_key(url: str) -> str:
    value = url.strip()
    if not value.lower().startswith("https://"):
        return value
    return value.rstrip("/") + "/"


def _homelab_icon_src_for_urls(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_icon_by_tunnel:
        return None
    for raw in urls:
        hit = homelab_icon_by_tunnel.get(_canonical_https_tunnel_key(raw))
        if hit:
            return hit
    return None


def _homelab_service_name_for_urls(
    urls: list[str],
    homelab_name_by_tunnel: dict[str, str] | None,
) -> str | None:
    if not homelab_name_by_tunnel:
        return None
    for raw in urls:
        hit = homelab_name_by_tunnel.get(_canonical_https_tunnel_key(raw))
        if hit:
            return hit
    return None


def _icon_filename(urls: list[str]) -> str:
    if not urls:
        return _validate_icon_filename("homepage.svg")
    parsed = urlparse(urls[0].strip())
    if parsed.port == 10443:
        return _validate_icon_filename("pfsense.svg")
    host = (parsed.hostname or "").strip().lower()
    if _ipv4_host(host):
        return _validate_icon_filename("pfsense.svg")
    return _validate_icon_filename("homepage.svg")


def _row_ui_metadata(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    pf_href = _pfsense_canonical_href(urls)
    if pf_href is not None:
        return {
            "display_label": "PfSense",
            "name": "PfSense",
            "href": pf_href,
            "tunnel_url": pf_href,
            "icon_filename": _validate_icon_filename("pfsense.svg"),
        }
    href = _row_href(urls).strip()
    catalog_name = _homelab_service_name_for_urls(urls, homelab_name_by_tunnel)
    display = catalog_name if catalog_name else _display_label(urls)
    icon_src = _homelab_icon_src_for_urls(urls, homelab_icon_by_tunnel)
    base: dict[str, Any] = {
        "display_label": display,
        "href": href,
        "tunnel_url": href,
        "icon_filename": _icon_filename(urls),
    }
    if catalog_name:
        base["name"] = catalog_name
    if icon_src:
        base["icon_src"] = icon_src
    return base


def _network_label(settings: APIDeploymentSettings) -> str:
    custom = (settings.sickz_network_label or "").strip()
    if custom:
        return custom
    return (APP_DOMAIN or "").strip() or "this deployment"


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


def _known_paas_runtime_detected() -> bool:
    env = os.environ
    return any(
        env.get(key) is not None and str(env.get(key)).strip() != ""
        for key in _KNOWN_PAAS_ENV_MARKERS
    )


def _implicit_internal_network(settings: APIDeploymentSettings) -> bool:
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return True
    return (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com"


def _internal_network_implicit(settings: APIDeploymentSettings) -> bool:
    if bool(settings.sickz_internal_network):
        return False
    return _implicit_internal_network(settings)


def _internal_network_inferred_from(settings: APIDeploymentSettings) -> str | None:
    if bool(settings.sickz_internal_network):
        return None
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "SICKZ_NETWORK_LABEL=nabla"
    if (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com":
        return "APP_DOMAIN=albandrieu.albandrieu.com"
    return None


def _internal_network_effective(settings: APIDeploymentSettings) -> bool:
    if _known_paas_runtime_detected():
        return False
    if bool(settings.sickz_internal_network):
        return True
    return _implicit_internal_network(settings)


def _skip_detail(settings: APIDeploymentSettings) -> str:
    if bool(settings.sickz_internal_network):
        return "Sickz probes are disabled (SICKZ_INTERNAL_NETWORK). This instance is treated as running on your home LAN where pfSense may be reachable."
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "Sickz probes are disabled: SICKZ_NETWORK_LABEL is 'nabla', so this instance is treated as on your home LAN."
    return "Sickz probes are disabled."


def _runtime_block(settings: APIDeploymentSettings) -> dict[str, Any]:
    return {
        "cloud_paas_detected": _known_paas_runtime_detected(),
        "sickz_internal_network_config": bool(settings.sickz_internal_network),
        "sickz_internal_network_implicit": _internal_network_implicit(settings),
        "internal_network_inferred_from": _internal_network_inferred_from(settings),
        "sickz_internal_network_effective": _internal_network_effective(settings),
    }


async def _probe_url(url: str) -> dict[str, Any]:
    """Probe HTTP(S) reachability with certificate verification intentionally off."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            verify=False,  # noqa: S501 — sickz must detect hosts with invalid certs
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "nabla-sickz-probe/1.0"},
            )
    except (httpx.HTTPError, OSError) as exc:
        return {"reachable": False, "error": normalize_probe_error(str(exc))}
    return {"reachable": True, "http_status": response.status_code}


async def _async_none() -> None:
    return None


async def _probe_alias_group(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Probe one logical target; any reachable alias makes the group reachable."""
    href = _row_href(urls)
    tls_coro = probe_https_tls_trusted(href) if href.lower().startswith("https:") else _async_none()
    pf_tcp_host = _pfsense_canonical_tcp_host(urls)
    if pf_tcp_host:
        tcp_coro = asyncio.gather(
            *(_probe_pfsense_tcp_port(pf_tcp_host, port) for port in _PFSENSE_EXTRA_TCP_PORTS),
        )
        results, tls_trusted, tcp_reachable = await asyncio.gather(
            asyncio.gather(*(_probe_url(url) for url in urls)),
            tls_coro,
            tcp_coro,
        )
    else:
        results, tls_trusted = await asyncio.gather(
            asyncio.gather(*(_probe_url(url) for url in urls)),
            tls_coro,
        )
        tcp_reachable = None

    by_url = {
        url: normalize_probe_result_errors(result)
        for url, result in zip(urls, results, strict=True)
    }
    out: dict[str, Any] = {
        "reachable": any(result.get("reachable") is True for result in results),
        "aliases_probed": urls,
        "alias_results": by_url,
        "tls_trusted": tls_trusted,
        **_row_ui_metadata(urls, homelab_icon_by_tunnel, homelab_name_by_tunnel),
    }
    if tcp_reachable is not None:
        out["pfsense_tcp_ports"] = {
            str(port): reachable
            for port, reachable in zip(_PFSENSE_EXTRA_TCP_PORTS, tcp_reachable, strict=True)
        }
        out["pfsense_tcp_port_policy"] = _pfsense_tcp_port_policy_payload()
        out["pfsense_tcp_ports_protocol_validated"] = True
    for result in results:
        if result.get("reachable") is True and result.get("http_status") is not None:
            out["http_status"] = result["http_status"]
            break
    return out


async def build_sickz_payload(request: Request) -> dict[str, Any]:
    """Build inverse-reachability results; reachable targets represent isolation failures."""
    settings = get_settings()
    network_label = _network_label(settings)
    runtime = _runtime_block(settings)
    homelab_icon_by_tunnel: dict[str, str] | None = None
    homelab_name_by_tunnel: dict[str, str] | None = None
    homelab_groups: list[list[str]] = []
    if _targets_equal_default_catalog_mode(settings.sickz_targets):
        (
            homelab_groups,
            homelab_icon_by_tunnel,
            homelab_name_by_tunnel,
        ) = await homelab_sickz_catalog_for_sickz()

    if _known_paas_runtime_detected() and (
        settings.sickz_internal_network or _implicit_internal_network(settings)
    ):
        _log.debug(
            "Home LAN skip would apply but a cloud/PaaS runtime was detected; sickz probes still run.",
        )

    groups = _ensure_pfsense_group(
        parse_sickz_target_groups(settings.sickz_targets) + homelab_groups,
    )
    if _internal_network_effective(settings):
        group_keys = [" | ".join(group) for group in groups]
        checks = {
            key: {
                "skipped": True,
                "aliases_probed": list(group),
                "reason": "Not probed (LAN / internal network skip).",
                "tls_trusted": None,
                **_row_ui_metadata(group, homelab_icon_by_tunnel, homelab_name_by_tunnel),
                **_pfsense_tcp_skip_payload(group),
            }
            for key, group in zip(group_keys, groups, strict=True)
        }
        return {
            "checks": checks,
            "version": request.app.version,
            "status": "skipped_internal_network",
            "network_label": network_label,
            "runtime": runtime,
            "detail": _skip_detail(settings),
        }

    if not groups:
        return {
            "checks": {},
            "version": request.app.version,
            "status": "no_targets",
            "network_label": network_label,
            "runtime": runtime,
            "detail": "SICKZ_TARGETS is empty; add comma- or newline-separated URL groups to probe.",
        }

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    group_keys = [" | ".join(group) for group in groups]
    group_results = await asyncio.gather(
        *(
            _probe_alias_group(group, homelab_icon_by_tunnel, homelab_name_by_tunnel)
            for group in groups
        ),
    )
    return {
        "checks": dict(zip(group_keys, group_results, strict=True)),
        "version": request.app.version,
        "network_label": network_label,
        "runtime": runtime,
    }
