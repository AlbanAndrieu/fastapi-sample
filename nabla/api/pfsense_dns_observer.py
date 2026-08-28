"""Read-only pfSense DNS posture observation for homelab health.

The observer intentionally projects only sanitized availability/policy facts. It never
returns credentials, raw pfSense configuration, DNS server addresses, aliases, or logs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from typing import Any, Literal

import httpx

from nabla.api.provider_credentials import inspect_environment_credentials

DNSPolicyState = Literal["ok", "warn", "fail", "unknown"]

_PFSENSE_TIMEOUT_SEC = 4.0
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_RUNNING_STATES = frozenset({"active", "healthy", "running", "started", "up"})
_STOPPED_STATES = frozenset({"crashed", "down", "error", "failed", "stopped"})


def pfsense_api_configuration_status() -> dict[str, object]:
    """Return sanitized presence and URL-validity state for the pfSense API."""
    status = inspect_environment_credentials(
        "pfsense",
        "PFSENSE_API_URL",
        "PFSENSE_API_KEY",
        secret_variables=frozenset({"PFSENSE_API_KEY"}),
    ).as_dict()
    base_url = os.getenv("PFSENSE_API_URL", "").strip()
    if status["configured"] and not base_url.lower().startswith(("https://", "http://")):
        status["configured"] = False
        status["configuration_stage"] = "invalid_configuration"
        status["invalid_configuration_variables"] = ["PFSENSE_API_URL"]
    else:
        status["invalid_configuration_variables"] = []
    return status


@dataclass(frozen=True, slots=True)
class PfSenseDNSSettings:
    """Credentials and transport policy for the read-only pfSense REST API."""

    base_url: str
    api_key: str
    verify_ssl: bool = True

    @classmethod
    def from_environment(cls) -> PfSenseDNSSettings | None:
        """Return settings only when the API URL and canonical key are validly configured."""
        status = pfsense_api_configuration_status()
        if status["configured"] is not True:
            return None

        base_url = os.getenv("PFSENSE_API_URL", "").strip().rstrip("/")
        api_key = os.getenv("PFSENSE_API_KEY", "").strip()
        raw_verify = os.getenv("PFSENSE_API_VERIFY_SSL", "true").strip().lower()
        verify_ssl = raw_verify not in _FALSE_VALUES
        return cls(base_url=base_url, api_key=api_key, verify_ssl=verify_ssl)


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return None


def _response_data(payload: object) -> object:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _safe_error(exc: BaseException) -> str:
    """Return a public diagnostic without leaking a private pfSense URL."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return exc.__class__.__name__


def _service_running(services: object) -> bool | None:
    if not isinstance(services, list):
        return None
    for row in services:
        if not isinstance(row, dict):
            continue
        identity = " ".join(
            str(row.get(key) or "")
            for key in ("name", "service", "description", "title")
        ).casefold()
        if "unbound" not in identity and "dns resolver" not in identity:
            continue

        for key in ("running", "active", "enabled"):
            parsed = _optional_bool(row.get(key))
            if parsed is not None:
                return parsed
        status = str(row.get("status") or row.get("state") or "").strip().casefold()
        if status in _RUNNING_STATES:
            return True
        if status in _STOPPED_STATES:
            return False
        return None
    return None


def _dns_upstreams(system_dns: object) -> tuple[str, ...]:
    if not isinstance(system_dns, dict):
        return ()
    raw = system_dns.get("dnsserver")
    if not isinstance(raw, list):
        return ()
    return tuple(str(value).strip() for value in raw if str(value).strip())


def _independent_from_truenas(
    *,
    forwarding: bool | None,
    upstreams: tuple[str, ...],
    truenas_hosts: frozenset[str],
) -> tuple[bool | None, bool | None]:
    """Determine whether pfSense DNS keeps a non-TrueNAS resolution path."""
    if forwarding is False:
        return True, False
    if forwarding is not True or not upstreams:
        return None, None

    normalized_truenas = {host.strip().casefold() for host in truenas_hosts if host.strip()}
    if not normalized_truenas:
        return None, None
    truenas_only = all(server.casefold() in normalized_truenas for server in upstreams)
    return not truenas_only, truenas_only


def _policy_state(
    *,
    resolver_enabled: bool | None,
    resolver_running: bool | None,
    independent_from_truenas: bool | None,
) -> tuple[DNSPolicyState, str]:
    if resolver_enabled is False:
        return "fail", "pfSense DNS Resolver is disabled"
    if resolver_running is False:
        return "fail", "pfSense DNS Resolver is not running"
    if resolver_enabled is None or resolver_running is None:
        return "unknown", "pfSense DNS Resolver state is incomplete"
    if independent_from_truenas is False:
        return "warn", "pfSense forwarding depends only on TrueNAS-hosted DNS"
    if independent_from_truenas is None:
        return "warn", "pfSense DNS is running but upstream independence is unverified"
    return "ok", "pfSense DNS Resolver is running with a TrueNAS-independent path"


async def _get_data(client: httpx.AsyncClient, path: str) -> object:
    response = await client.get(path)
    response.raise_for_status()
    return _response_data(response.json())


async def observe_pfsense_dns_posture(
    *,
    truenas_hosts: frozenset[str] = frozenset(),
    settings: PfSenseDNSSettings | None = None,
) -> dict[str, Any]:
    """Return sanitized pfSense/Unbound DNS policy evidence."""
    configuration = pfsense_api_configuration_status() if settings is None else None
    configured = settings or PfSenseDNSSettings.from_environment()
    if configured is None:
        return {
            **(configuration or {}),
            "configured": False,
            "reachable": None,
            "policy_state": "unknown",
            "reason": "pfSense API observation is not configured",
        }

    timeout = httpx.Timeout(_PFSENSE_TIMEOUT_SEC)
    async with httpx.AsyncClient(
        base_url=configured.base_url,
        headers={"X-API-Key": configured.api_key, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
        verify=configured.verify_ssl,
    ) as client:
        paths = {
            "system": "/api/v2/status/system",
            "services": "/api/v2/status/services",
            "resolver": "/api/v2/services/dns_resolver/settings",
            "system_dns": "/api/v2/system/dns",
        }
        results = await asyncio.gather(
            *(_get_data(client, path) for path in paths.values()),
            return_exceptions=True,
        )

    observed = dict(zip(paths, results, strict=True))
    system_result = observed["system"]
    if isinstance(system_result, BaseException):
        return {
            "configured": True,
            "reachable": False,
            "policy_state": "unknown",
            "reason": "pfSense API is unreachable from this runtime",
            "error_stage": "system",
            "error": _safe_error(system_result),
        }

    failed_stage = next(
        (
            name
            for name in ("services", "resolver", "system_dns")
            if isinstance(observed[name], BaseException)
        ),
        None,
    )
    if failed_stage is not None:
        error = observed[failed_stage]
        error_text = _safe_error(error) if isinstance(error, BaseException) else "unknown"
        return {
            "configured": True,
            "reachable": True,
            "policy_state": "unknown",
            "reason": "pfSense DNS policy evidence is incomplete",
            "error_stage": failed_stage,
            "error": error_text,
        }

    resolver = observed["resolver"]
    resolver_data = resolver if isinstance(resolver, dict) else {}
    resolver_enabled = _optional_bool(resolver_data.get("enable"))
    forwarding = _optional_bool(resolver_data.get("forwarding"))
    forward_tls = _optional_bool(resolver_data.get("forward_tls_upstream"))
    resolver_running = _service_running(observed["services"])
    upstreams = _dns_upstreams(observed["system_dns"])
    independent, truenas_only = _independent_from_truenas(
        forwarding=forwarding,
        upstreams=upstreams,
        truenas_hosts=truenas_hosts,
    )
    policy_state, reason = _policy_state(
        resolver_enabled=resolver_enabled,
        resolver_running=resolver_running,
        independent_from_truenas=independent,
    )

    port = resolver_data.get("port")
    return {
        "configured": True,
        "reachable": True,
        "policy_state": policy_state,
        "reason": reason,
        "resolver": {
            "enabled": resolver_enabled,
            "running": resolver_running,
            "forwarding": forwarding,
            "forward_tls_upstream": forward_tls,
            "port": int(port) if isinstance(port, int | str) and str(port).isdigit() else None,
        },
        "upstream": {
            "count": len(upstreams),
            "independent_from_truenas": independent,
            "truenas_only": truenas_only,
        },
    }
