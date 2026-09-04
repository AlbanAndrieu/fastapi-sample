"""Read-only pfSense DNS posture observation for homelab health."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from typing import Any, Literal

import httpx

from nabla.api.external_probe_cache import get_or_refresh_probe
from nabla.api.provider_probe_policies import (
    PFSENSE_POSTURE_CACHE_POLICY as _PFSENSE_POSTURE_CACHE_POLICY,
)
from nabla.api.pfsense_security_observer import observe_pfsense_ingress_block
from nabla.api.provider_credentials import inspect_environment_credentials

DNSPolicyState = Literal["ok", "warn", "fail", "unknown"]

_PFSENSE_CONNECT_TIMEOUT_SEC = 2.0
_PFSENSE_READ_TIMEOUT_SEC = 4.0
_PFSENSE_POSTURE_DEADLINE_SEC = 8.0
_PFSENSE_MAX_CONCURRENCY = 2
_PFSENSE_POSTURE_CACHE_KEY = "pfsense:posture"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_RUNNING_STATES = frozenset({"active", "healthy", "running", "started", "up"})
_STOPPED_STATES = frozenset({"crashed", "down", "error", "failed", "stopped"})
_SECURITY_SERVICE_MATCHERS = {
    "snort": ("snort",),
    "pfblockerng": ("pfblocker", "pfb_filter", "pfb_dnsbl"),
    "crowdsec": ("crowdsec",),
}
_SECURITY_SERVICE_LABELS = {
    "snort": "Snort",
    "pfblockerng": "pfBlockerNG",
    "crowdsec": "CrowdSec",
}


def _posture_environment_variables() -> tuple[str, str]:
    """Prefer dedicated posture credentials while retaining legacy compatibility."""
    url_var = (
        "PFSENSE_POSTURE_API_URL"
        if os.getenv("PFSENSE_POSTURE_API_URL", "").strip()
        else "PFSENSE_API_URL"
    )
    if os.getenv("PFSENSE_POSTURE_API_KEY", "").strip():
        key_var = "PFSENSE_POSTURE_API_KEY"
    elif os.getenv("PFSENSE_API_KEY", "").strip():
        key_var = "PFSENSE_API_KEY"
    else:
        key_var = "PFSENSE_POSTURE_API_KEY"
    return url_var, key_var


def pfsense_api_configuration_status() -> dict[str, object]:
    """Return sanitized presence and URL-validity state for posture observation."""
    url_var, key_var = _posture_environment_variables()
    status = inspect_environment_credentials(
        "pfsense",
        url_var,
        key_var,
        secret_variables=frozenset({key_var}),
    ).as_dict()
    base_url = os.getenv(url_var, "").strip()
    if status["configured"] and not base_url.lower().startswith(("https://", "http://")):
        status["configured"] = False
        status["configuration_stage"] = "invalid_configuration"
        status["invalid_configuration_variables"] = [url_var]
    else:
        status["invalid_configuration_variables"] = []
    status["credential_mode"] = (
        "dedicated_posture" if key_var == "PFSENSE_POSTURE_API_KEY" else "legacy_shared"
    )
    return status


@dataclass(frozen=True, slots=True)
class PfSenseDNSSettings:
    """Credentials and transport policy for read-only pfSense posture endpoints."""

    base_url: str
    api_key: str
    verify_ssl: bool = True

    @classmethod
    def from_environment(cls) -> PfSenseDNSSettings | None:
        status = pfsense_api_configuration_status()
        if status["configured"] is not True:
            return None
        url_var, key_var = _posture_environment_variables()
        raw_verify = os.getenv(
            "PFSENSE_POSTURE_API_VERIFY_SSL",
            os.getenv("PFSENSE_API_VERIFY_SSL", "true"),
        ).strip().lower()
        return cls(
            base_url=os.getenv(url_var, "").strip().rstrip("/"),
            api_key=os.getenv(key_var, "").strip(),
            verify_ssl=raw_verify not in _FALSE_VALUES,
        )


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
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return "timeout"
    return exc.__class__.__name__


def _service_identity(row: dict[str, Any]) -> str:
    normalized = str(row.get("identity") or "").strip().casefold()
    if normalized:
        return normalized
    return " ".join(
        str(row.get(key) or "")
        for key in ("name", "service", "description", "title")
    ).casefold()


def _service_runtime_state(row: dict[str, Any]) -> str:
    normalized = str(row.get("runtime_state") or "").strip().casefold()
    if normalized in {"running", "stopped", "unknown"}:
        return normalized
    for key in ("running", "active", "enabled"):
        parsed = _optional_bool(row.get(key))
        if parsed is not None:
            return "running" if parsed else "stopped"
    status = str(row.get("status") or row.get("state") or "").strip().casefold()
    if status in _RUNNING_STATES:
        return "running"
    if status in _STOPPED_STATES:
        return "stopped"
    return "unknown"


def _sanitize_services(services: object) -> list[dict[str, str]]:
    if not isinstance(services, list):
        return []
    return [
        {
            "identity": _service_identity(row),
            "runtime_state": _service_runtime_state(row),
        }
        for row in services
        if isinstance(row, dict)
    ]


def _service_running(services: object) -> bool | None:
    if not isinstance(services, list):
        return None
    for row in services:
        if not isinstance(row, dict):
            continue
        identity = _service_identity(row)
        if "unbound" not in identity and "dns resolver" not in identity:
            continue
        state = _service_runtime_state(row)
        if state == "running":
            return True
        if state == "stopped":
            return False
        return None
    return None


def _security_filter_observations(
    services: object,
    *,
    ingress_block: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    ingress_state = str((ingress_block or {}).get("state") or "unknown")
    snort_blocked = ingress_state == "blocked"
    filters: list[dict[str, str]] = [
        {
            "id": "firewall",
            "label": "pfSense/PF firewall",
            "state": "blocked" if snort_blocked else "in_path",
            "detail": (
                "PF is enforcing the snort2c block for the observed FastAPI egress"
                if snort_blocked
                else "PF is on the WAN ingress path; the exact matching rule is not attributed"
            ),
        }
    ]
    service_rows = [
        row for row in services if isinstance(row, dict)
    ] if isinstance(services, list) else []
    for filter_id, matchers in _SECURITY_SERVICE_MATCHERS.items():
        matches = [
            row
            for row in service_rows
            if any(matcher in _service_identity(row) for matcher in matchers)
        ]
        if filter_id == "snort" and snort_blocked:
            state = "blocked"
            detail = "Observed FastAPI egress is present in the Snort snort2c PF table"
        elif matches:
            states = {_service_runtime_state(row) for row in matches}
            if "running" in states:
                state = "running"
            elif states == {"stopped"}:
                state = "stopped"
            else:
                state = "unknown"
            detail = f"{len(matches)} service entr{'y' if len(matches) == 1 else 'ies'} observed"
        elif filter_id == "snort" and ingress_state == "clear":
            state = "clear"
            detail = "snort2c telemetry is reachable and the observed FastAPI egress is not blocked"
        elif filter_id == "snort" and ingress_state in {
            "attribution_unavailable",
            "telemetry_stale",
        }:
            state = "observed"
            detail = "snort2c telemetry exists but current egress attribution is not authoritative"
        elif filter_id == "snort" and ingress_state == "telemetry_unavailable":
            state = "unknown"
            detail = "snort2c telemetry is unavailable"
        else:
            state = "not_observed"
            detail = "Not exposed by /api/v2/status/services"
        filters.append(
            {
                "id": filter_id,
                "label": _SECURITY_SERVICE_LABELS[filter_id],
                "state": state,
                "detail": detail,
            }
        )
    return filters


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
    if forwarding is False:
        return True, False
    if forwarding is not True or not upstreams:
        return None, None
    normalized = {host.strip().casefold() for host in truenas_hosts if host.strip()}
    if not normalized:
        return None, None
    truenas_only = all(server.casefold() in normalized for server in upstreams)
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


async def _bounded_observations(
    client: httpx.AsyncClient,
    paths: dict[str, str],
) -> dict[str, object | BaseException]:
    semaphore = asyncio.Semaphore(_PFSENSE_MAX_CONCURRENCY)

    async def fetch(path: str) -> object:
        async with semaphore:
            return await _get_data(client, path)

    results = await asyncio.gather(
        *(fetch(path) for path in paths.values()),
        return_exceptions=True,
    )
    return dict(zip(paths, results, strict=True))


def _resolver_payload(value: object) -> dict[str, Any]:
    resolver = value if isinstance(value, dict) else {}
    port = resolver.get("port")
    return {
        "enabled": _optional_bool(resolver.get("enable")),
        "forwarding": _optional_bool(resolver.get("forwarding")),
        "forward_tls_upstream": _optional_bool(resolver.get("forward_tls_upstream")),
        "port": int(port) if isinstance(port, int | str) and str(port).isdigit() else None,
    }


async def _observe_posture_origin_bounded(
    settings: PfSenseDNSSettings,
) -> dict[str, Any]:
    paths = {
        "system": "/api/v2/system/version",
        "services": "/api/v2/status/services",
        "resolver": "/api/v2/services/dns_resolver/settings",
        "system_dns": "/api/v2/system/dns",
    }
    timeout = httpx.Timeout(
        connect=_PFSENSE_CONNECT_TIMEOUT_SEC,
        read=_PFSENSE_READ_TIMEOUT_SEC,
        write=_PFSENSE_CONNECT_TIMEOUT_SEC,
        pool=_PFSENSE_CONNECT_TIMEOUT_SEC,
    )
    async with httpx.AsyncClient(
        base_url=settings.base_url,
        headers={"X-API-Key": settings.api_key, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
        verify=settings.verify_ssl,
    ) as client:
        try:
            await _get_data(client, paths["system"])
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "reachable": False,
                "error_stage": "system",
                "error": _safe_error(exc),
                "services": [],
                "resolver": {},
                "upstreams": [],
            }
        remaining = await _bounded_observations(
            client,
            {name: path for name, path in paths.items() if name != "system"},
        )

    failure = next(
        (
            (name, value)
            for name, value in remaining.items()
            if isinstance(value, BaseException)
        ),
        None,
    )
    services = remaining.get("services")
    resolver = remaining.get("resolver")
    system_dns = remaining.get("system_dns")
    result: dict[str, Any] = {
        "reachable": True,
        "services": _sanitize_services(
            None if isinstance(services, BaseException) else services
        ),
        "resolver": _resolver_payload(
            None if isinstance(resolver, BaseException) else resolver
        ),
        "upstreams": list(
            _dns_upstreams(
                None if isinstance(system_dns, BaseException) else system_dns
            )
        ),
    }
    if failure is not None:
        stage, error = failure
        result["error_stage"] = stage
        result["error"] = _safe_error(error)
    return result


async def _observe_posture_origin(settings: PfSenseDNSSettings) -> dict[str, Any]:
    try:
        async with asyncio.timeout(_PFSENSE_POSTURE_DEADLINE_SEC):
            return await _observe_posture_origin_bounded(settings)
    except TimeoutError:
        return {
            "reachable": False,
            "error_stage": "deadline",
            "error": "timeout",
            "services": [],
            "resolver": {},
            "upstreams": [],
        }


def _posture_success(value: dict[str, Any]) -> bool:
    return value.get("reachable") is True and not value.get("error_stage")


async def _cached_posture(settings: PfSenseDNSSettings) -> dict[str, Any]:
    cached = await get_or_refresh_probe(
        _PFSENSE_POSTURE_CACHE_KEY,
        lambda: _observe_posture_origin(settings),
        is_success=_posture_success,
        policy=_PFSENSE_POSTURE_CACHE_POLICY,
    )
    current = dict(cached.value)
    current_failure = current.get("reachable") is False or bool(current.get("error_stage"))
    if (current_failure or cached.metadata.get("stale") is True) and cached.last_good:
        result = dict(cached.last_good)
        result["stale"] = True
        result["refresh_error_stage"] = current.get("error_stage")
        result["refresh_error"] = current.get("error") or "posture refresh in progress"
    else:
        result = current
        result["stale"] = False
    result["cache"] = cached.metadata
    return result


async def observe_pfsense_dns_posture(
    *,
    truenas_hosts: frozenset[str] = frozenset(),
    settings: PfSenseDNSSettings | None = None,
) -> dict[str, Any]:
    """Return cached posture plus egress-specific Snort/PF evidence."""
    configuration = pfsense_api_configuration_status() if settings is None else None
    configured = settings or PfSenseDNSSettings.from_environment()
    if configured is None:
        ingress = await observe_pfsense_ingress_block()
        return {
            **(configuration or {}),
            "configured": False,
            "reachable": None,
            "policy_state": "unknown",
            "reason": "pfSense posture observation is not configured",
            "security_filters": _security_filter_observations(None, ingress_block=ingress),
            "ingress_block": ingress,
        }

    if settings is not None:
        posture_task = asyncio.create_task(_observe_posture_origin(configured))
    else:
        posture_task = asyncio.create_task(_cached_posture(configured))
    ingress_task = asyncio.create_task(observe_pfsense_ingress_block())
    posture, ingress = await asyncio.gather(posture_task, ingress_task)

    services = posture.get("services", [])
    filters = _security_filter_observations(services, ingress_block=ingress)
    if posture.get("reachable") is not True:
        return {
            "configured": True,
            "reachable": False,
            "policy_state": "unknown",
            "reason": "pfSense posture API is unreachable from this runtime",
            "error_stage": posture.get("error_stage", "system"),
            "error": posture.get("error", "unknown"),
            "security_filters": filters,
            "ingress_block": ingress,
            **({"cache": posture["cache"]} if "cache" in posture else {}),
        }
    if posture.get("error_stage"):
        return {
            "configured": True,
            "reachable": True,
            "policy_state": "unknown",
            "reason": "pfSense DNS policy evidence is incomplete",
            "error_stage": posture["error_stage"],
            "error": posture.get("error", "unknown"),
            "security_filters": filters,
            "ingress_block": ingress,
        }

    resolver = posture.get("resolver") if isinstance(posture.get("resolver"), dict) else {}
    forwarding = _optional_bool(resolver.get("forwarding"))
    upstreams = tuple(str(value) for value in posture.get("upstreams", []))
    independent, truenas_only = _independent_from_truenas(
        forwarding=forwarding,
        upstreams=upstreams,
        truenas_hosts=truenas_hosts,
    )
    resolver_running = _service_running(services)
    policy_state, reason = _policy_state(
        resolver_enabled=_optional_bool(resolver.get("enabled")),
        resolver_running=resolver_running,
        independent_from_truenas=independent,
    )
    result: dict[str, Any] = {
        "configured": True,
        "reachable": True,
        "policy_state": policy_state,
        "reason": reason,
        "resolver": {
            **resolver,
            "running": resolver_running,
        },
        "upstream": {
            "count": len(upstreams),
            "independent_from_truenas": independent,
            "truenas_only": truenas_only,
        },
        "security_filters": filters,
        "ingress_block": ingress,
    }
    if posture.get("stale") is True:
        result["stale"] = True
        result["refresh_error"] = posture.get("refresh_error")
        result["refresh_error_stage"] = posture.get("refresh_error_stage")
    if "cache" in posture:
        result["cache"] = posture["cache"]
    return result
