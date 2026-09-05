"""Inverse-reachability probes for the ``/sickz`` endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import urllib3
from fastapi import Request

from nabla.api.health_probe_utils import (
    normalize_probe_error,
    normalize_probe_result_errors,
    probe_https_tls_trusted,
)
from nabla.api.homelab_catalog import homelab_sickz_catalog_for_sickz
from nabla.api.probe_budget import ProbeBudget
from nabla.api.runtime_environment import known_paas_runtime_detected
from nabla.api.sickz_pfsense import (
    PFSENSE_EXTRA_TCP_PORTS,
    ensure_pfsense_group,
    pfsense_canonical_href,
    pfsense_canonical_tcp_host,
    pfsense_tcp_port_policy_payload,
    pfsense_tcp_skip_payload,
    probe_pfsense_tcp_port,
)
from nabla.api.sickz_row_metadata import row_href, row_ui_metadata
from nabla.config_settings import (
    APP_DOMAIN,
    APIDeploymentSettings,
    _default_sickz_targets_value,
    get_settings,
)

_log = logging.getLogger(__name__)

_SICKZ_PROBE_DEADLINE_SEC = 8.0
_SICKZ_MAX_CONCURRENCY = 4


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


def _network_label(settings: APIDeploymentSettings) -> str:
    custom = (settings.sickz_network_label or "").strip()
    if custom:
        return custom
    return (APP_DOMAIN or "").strip() or "this deployment"


def _implicit_internal_network(settings: APIDeploymentSettings) -> bool:
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return True
    return (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com"


def _internal_network_implicit(settings: APIDeploymentSettings) -> bool:
    if bool(settings.sickz_internal_network):
        return False
    return _implicit_internal_network(settings)


def _internal_network_inferred_from(
    settings: APIDeploymentSettings,
) -> str | None:
    if bool(settings.sickz_internal_network):
        return None
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return "SICKZ_NETWORK_LABEL=nabla"
    if (APP_DOMAIN or "").strip().lower() == "albandrieu.albandrieu.com":
        return "APP_DOMAIN=albandrieu.albandrieu.com"
    return None


def _internal_network_effective(settings: APIDeploymentSettings) -> bool:
    if known_paas_runtime_detected():
        return False
    if bool(settings.sickz_internal_network):
        return True
    return _implicit_internal_network(settings)


def _skip_detail(settings: APIDeploymentSettings) -> str:
    if bool(settings.sickz_internal_network):
        return (
            "Sickz probes are disabled (SICKZ_INTERNAL_NETWORK). This instance "
            "is treated as running on your home LAN where pfSense may be reachable."
        )
    if (settings.sickz_network_label or "").strip().lower() == "nabla":
        return (
            "Sickz probes are disabled: SICKZ_NETWORK_LABEL is 'nabla', so this "
            "instance is treated as on your home LAN."
        )
    return "Sickz probes are disabled."


def _runtime_block(settings: APIDeploymentSettings) -> dict[str, Any]:
    return {
        "cloud_paas_detected": known_paas_runtime_detected(),
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
        return {
            "reachable": False,
            "error": normalize_probe_error(str(exc)),
        }
    return {"reachable": True, "http_status": response.status_code}


async def _async_none() -> None:
    return None


async def _probe_alias_group(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None = None,
    homelab_name_by_tunnel: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Probe one logical target; any reachable alias makes the group reachable."""
    href = row_href(urls)
    pf_tcp_host = pfsense_canonical_tcp_host(urls)
    paas_pfsense = bool(pf_tcp_host and known_paas_runtime_detected())
    if paas_pfsense:
        canonical = pfsense_canonical_href(urls)
        probe_urls = [canonical] if canonical else []
        tls_coro = _async_none()
    else:
        probe_urls = list(urls)
        tls_coro = (
            probe_https_tls_trusted(href)
            if href.lower().startswith("https:")
            else _async_none()
        )

    if pf_tcp_host:
        tcp_coro = asyncio.gather(
            *(
                probe_pfsense_tcp_port(pf_tcp_host, port)
                for port in PFSENSE_EXTRA_TCP_PORTS
            ),
        )
        results, tls_trusted, tcp_reachable = await asyncio.gather(
            asyncio.gather(*(_probe_url(url) for url in probe_urls)),
            tls_coro,
            tcp_coro,
        )
    else:
        results, tls_trusted = await asyncio.gather(
            asyncio.gather(*(_probe_url(url) for url in probe_urls)),
            tls_coro,
        )
        tcp_reachable = None

    by_url = {
        url: {
            "reachable": None,
            "skipped": True,
            "reason": "non-canonical pfSense alias skipped from cloud exposure probing",
        }
        for url in urls
        if url not in probe_urls
    }
    by_url.update(
        {
            url: normalize_probe_result_errors(result)
            for url, result in zip(probe_urls, results, strict=True)
        }
    )
    out: dict[str, Any] = {
        "reachable": any(
            result.get("reachable") is True for result in results
        ),
        "aliases_probed": probe_urls,
        "aliases_configured": urls,
        "alias_results": by_url,
        "tls_trusted": tls_trusted,
        **row_ui_metadata(
            urls,
            homelab_icon_by_tunnel,
            homelab_name_by_tunnel,
        ),
    }
    if tcp_reachable is not None:
        out["pfsense_tcp_ports"] = {
            str(port): reachable
            for port, reachable in zip(
                PFSENSE_EXTRA_TCP_PORTS,
                tcp_reachable,
                strict=True,
            )
        }
        out["pfsense_tcp_port_policy"] = pfsense_tcp_port_policy_payload()
        out["pfsense_tcp_ports_protocol_validated"] = True
    for result in results:
        if (
            result.get("reachable") is True
            and result.get("http_status") is not None
        ):
            out["http_status"] = result["http_status"]
            break
    return out


def _deadline_group_result(
    urls: list[str],
    homelab_icon_by_tunnel: dict[str, str] | None,
    homelab_name_by_tunnel: dict[str, str] | None,
) -> dict[str, Any]:
    """Return unknown exposure evidence when the aggregate sickz budget expires."""
    return {
        "reachable": None,
        "timed_out": True,
        "error": "aggregate sickz probe deadline exceeded",
        "error_kind": "deadline",
        "aliases_probed": list(urls),
        "alias_results": {
            url: {
                "reachable": None,
                "timed_out": True,
                "error_kind": "deadline",
            }
            for url in urls
        },
        "tls_trusted": None,
        **row_ui_metadata(
            urls,
            homelab_icon_by_tunnel,
            homelab_name_by_tunnel,
        ),
    }


async def build_sickz_payload(request: Request) -> dict[str, Any]:
    """Build inverse-reachability results for exposure-policy validation."""
    settings = get_settings()
    network_label = _network_label(settings)
    runtime = _runtime_block(settings)
    budget = ProbeBudget(
        deadline_seconds=_SICKZ_PROBE_DEADLINE_SEC,
        max_concurrency=_SICKZ_MAX_CONCURRENCY,
    )
    homelab_icon_by_tunnel: dict[str, str] | None = None
    homelab_name_by_tunnel: dict[str, str] | None = None
    homelab_groups: list[list[str]] = []
    catalog_timed_out = False
    if _targets_equal_default_catalog_mode(settings.sickz_targets):
        catalog = await budget.run(
            homelab_sickz_catalog_for_sickz,
            timeout_value=lambda: None,
        )
        if catalog is None:
            catalog_timed_out = True
        else:
            (
                homelab_groups,
                homelab_icon_by_tunnel,
                homelab_name_by_tunnel,
            ) = catalog

    if known_paas_runtime_detected() and (
        settings.sickz_internal_network
        or _implicit_internal_network(settings)
    ):
        _log.debug(
            "Home LAN skip would apply but a cloud/PaaS runtime was detected; "
            "sickz probes still run.",
        )

    groups = ensure_pfsense_group(
        parse_sickz_target_groups(settings.sickz_targets) + homelab_groups,
        default_targets=_default_sickz_targets_value(),
    )
    if _internal_network_effective(settings):
        group_keys = [" | ".join(group) for group in groups]
        checks = {
            key: {
                "skipped": True,
                "aliases_probed": list(group),
                "reason": "Not probed (LAN / internal network skip).",
                "tls_trusted": None,
                **row_ui_metadata(
                    group,
                    homelab_icon_by_tunnel,
                    homelab_name_by_tunnel,
                ),
                **pfsense_tcp_skip_payload(group),
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
            "detail": (
                "SICKZ_TARGETS is empty; add comma- or newline-separated "
                "URL groups to probe."
            ),
        }

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    group_keys = [" | ".join(group) for group in groups]
    group_results = await asyncio.gather(
        *(
            budget.run(
                lambda group=group: _probe_alias_group(
                    group,
                    homelab_icon_by_tunnel,
                    homelab_name_by_tunnel,
                ),
                timeout_value=lambda group=group: _deadline_group_result(
                    group,
                    homelab_icon_by_tunnel,
                    homelab_name_by_tunnel,
                ),
            )
            for group in groups
        ),
    )
    checks = dict(zip(group_keys, group_results, strict=True))
    if catalog_timed_out:
        checks["homelab_catalog"] = {
            "reachable": None,
            "timed_out": True,
            "error": "aggregate sickz catalog deadline exceeded",
            "error_kind": "deadline",
        }
    return {
        "checks": checks,
        "version": request.app.version,
        "network_label": network_label,
        "runtime": runtime,
        "probe_budget": {
            "deadline_seconds": _SICKZ_PROBE_DEADLINE_SEC,
            "max_concurrency": _SICKZ_MAX_CONCURRENCY,
        },
    }
