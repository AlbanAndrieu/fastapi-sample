"""Least-privilege read-only pfSense/Snort ingress-block observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import ssl
import time
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from nabla.api.external_probe_cache import get_or_refresh_probe, reset_probe_cache
from nabla.api.provider_probe_policies import (
    PFSENSE_SNORT2C_CACHE_POLICY as _SNORT2C_CACHE_POLICY,
)
from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.public_egress_observer import observe_public_egress_ip
from nabla.api.truenas_transport_diagnostics import homelab_wan_metadata
from nabla.settings.homelab import (
    PfSenseSecurityProviderSettings,
    pfsense_invalid_configuration_variables,
    pfsense_security_environment_variables,
)

ControlPathMode = Literal["shared_wan", "out_of_band"]
_PFSENSE_CONNECT_TIMEOUT_SEC = 2.0
_PFSENSE_READ_TIMEOUT_SEC = 8.0
_PFSENSE_MAX_ATTEMPTS = 1
_PFSENSE_RETRY_DELAY_SEC = 0.2
_SNORT2C_PATH = "/api/v2/diagnostics/table?id=snort2c"
_SNORT2C_CACHE_KEY = "pfsense:snort2c"
_TRUENAS_PUBLIC_PORT = 7000


@dataclass(frozen=True, slots=True)
class PfSenseSecuritySettings:
    """Dedicated credentials for GET-only security telemetry."""

    base_url: str
    api_key: str
    verify_ssl: bool = True
    control_path_mode: ControlPathMode = "shared_wan"

    @classmethod
    def from_environment(cls) -> PfSenseSecuritySettings | None:
        """Load validated security transport with an explicit legacy fallback."""
        status = security_configuration_status()
        if status["configured"] is not True:
            return None
        try:
            provider = PfSenseSecurityProviderSettings()
        except ValidationError:
            return None
        return cls(
            base_url=str(provider.api_url).rstrip("/"),
            api_key=provider.api_key.get_secret_value(),
            verify_ssl=provider.verify_ssl,
            control_path_mode=provider.security_path_mode,
        )


def security_configuration_status() -> dict[str, Any]:
    """Return the security observer configuration contract without secrets."""
    status = inspect_environment_credentials(
        provider="pfsense_security",
        required_variables=pfsense_security_environment_variables(),
        invalid_variables=pfsense_invalid_configuration_variables(),
        dedicated_credential="PFSENSE_SECURITY_API_KEY",
        legacy_credential="PFSENSE_API_KEY",
    )
    status.update(
        {
            "required_privilege": "api-v2-diagnostics-table-get",
            "write_privileges_required": False,
        }
    )
    return status


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=_PFSENSE_CONNECT_TIMEOUT_SEC,
        read=_PFSENSE_READ_TIMEOUT_SEC,
        write=_PFSENSE_CONNECT_TIMEOUT_SEC,
        pool=_PFSENSE_CONNECT_TIMEOUT_SEC,
    )


def _control_path(settings: PfSenseSecuritySettings) -> dict[str, Any]:
    independent = settings.control_path_mode == "out_of_band"
    return {
        "mode": settings.control_path_mode,
        "independent_from_wan_filter": independent,
        "blind_spot": not independent,
        "detail": (
            "Security telemetry uses an independent control channel"
            if independent
            else "Security telemetry shares the pfSense WAN path and is not an independent control channel"
        ),
    }


def _base_evidence(settings: PfSenseSecuritySettings) -> dict[str, Any]:
    wan = homelab_wan_metadata()
    return {
        "engine": "snort",
        "firewall": "pfSense/PF",
        "mechanism": "snort2c",
        "destination": {
            "ip": wan.get("public_ip"),
            "port": _TRUENAS_PUBLIC_PORT,
            "role": "pfSense WAN / homelab public endpoint",
        },
        "control_path": _control_path(settings),
        "path": _SNORT2C_PATH,
    }


def _table_entries(table: dict[str, Any]) -> list[str]:
    raw = table.get("entries", [])
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    if not isinstance(raw, list):
        return []
    entries: list[str] = []
    for item in raw:
        value = str(item).strip()
        try:
            entries.append(str(ipaddress.ip_address(value)))
        except ValueError:
            continue
    return entries


def _block_evidence(
    *,
    table: dict[str, Any],
    egress: dict[str, Any],
    settings: PfSenseSecuritySettings,
) -> dict[str, Any]:
    entries = _table_entries(table)
    ip_value = str(egress.get("ip") or "").strip()
    matched = ip_value in entries if ip_value else False
    evidence = _base_evidence(settings)
    evidence.update(
        {
            "state": "blocked" if matched else "clear",
            "telemetry_available": True,
            "attribution_available": True,
            "source": {
                "ip": ip_value or None,
                "role": "FastAPI Cloud egress (observed)",
            },
            "table_entry_count": len(entries),
            "match": matched,
            "evidence": (
                "Observed FastAPI Cloud egress is present in pfSense snort2c"
                if matched
                else "Observed FastAPI Cloud egress is absent from pfSense snort2c"
            ),
        }
    )
    return evidence


def _attribution_unavailable(
    *,
    table: dict[str, Any],
    settings: PfSenseSecuritySettings,
) -> dict[str, Any]:
    evidence = _base_evidence(settings)
    evidence.update(
        {
            "state": "attribution_unavailable",
            "telemetry_available": True,
            "attribution_available": False,
            "table_entry_count": len(_table_entries(table)),
            "match": None,
            "evidence": "snort2c is readable but FastAPI Cloud egress identity is unavailable",
        }
    )
    return evidence


def _unavailable(
    settings: PfSenseSecuritySettings,
    error: str,
    *,
    error_kind: str | None = None,
    failure_stage: str | None = None,
    exception_type: str | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    evidence = _base_evidence(settings)
    evidence.update(
        {
            "state": "telemetry_unavailable",
            "telemetry_available": False,
            "attribution_available": False,
            "table_entry_count": None,
            "match": None,
            "evidence": error,
            "error_kind": error_kind,
            "failure_stage": failure_stage,
            "exception_type": exception_type,
            "elapsed_ms": elapsed_ms,
        }
    )
    return evidence


def _classified_transport_error(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout", "connect", type(exc).__name__
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout", "response", type(exc).__name__
    if isinstance(exc, httpx.ConnectError):
        cause = exc.__cause__
        if isinstance(cause, ssl.SSLError):
            return "tls_error", "tls", type(exc).__name__
        return "connect_error", "connect", type(exc).__name__
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "auth_error", "authentication", type(exc).__name__
        return "http_error", "response", type(exc).__name__
    if isinstance(exc, httpx.HTTPError):
        return "http_error", "response", type(exc).__name__
    return "observer_error", "observer", type(exc).__name__


async def _fetch_snort2c_table(settings: PfSenseSecuritySettings) -> dict[str, Any]:
    started = time.monotonic()
    headers = {"X-API-Key": settings.api_key}
    async with httpx.AsyncClient(
        base_url=settings.base_url,
        headers=headers,
        verify=settings.verify_ssl,
        timeout=_timeout(),
        follow_redirects=False,
    ) as client:
        response = await client.get(_SNORT2C_PATH)
        response.raise_for_status()
        payload = response.json()
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if isinstance(payload, dict):
        payload.setdefault("elapsed_ms", elapsed_ms)
        payload.setdefault("attempts", 1)
        return payload
    return {"entries": [], "elapsed_ms": elapsed_ms, "attempts": 1}


async def _refresh_security_observation(
    settings: PfSenseSecuritySettings,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        table = await _fetch_snort2c_table(settings)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        error_kind, failure_stage, exception_type = _classified_transport_error(exc)
        return _unavailable(
            settings,
            f"snort2c telemetry unavailable: {exception_type}",
            error_kind=error_kind,
            failure_stage=failure_stage,
            exception_type=exception_type,
            elapsed_ms=elapsed_ms,
        )
    try:
        egress = await observe_public_egress_ip()
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        egress = {"ip": None, "observed": False}
    if egress.get("ip"):
        result = _block_evidence(table=table, egress=egress, settings=settings)
    else:
        result = _attribution_unavailable(table=table, settings=settings)
    result["attempts"] = table.get("attempts", 1)
    result["elapsed_ms"] = table.get("elapsed_ms")
    return result


async def observe_pfsense_ingress_block() -> dict[str, Any]:
    """Return cached Snort/PF ingress-block evidence for the current cloud egress."""
    settings = PfSenseSecuritySettings.from_environment()
    if settings is None:
        return {
            "state": "telemetry_unavailable",
            "telemetry_available": False,
            "attribution_available": False,
            "evidence": "pfSense security observer is not configured",
            "configuration": security_configuration_status(),
        }

    async def refresh() -> dict[str, Any]:
        return await _refresh_security_observation(settings)

    result = await get_or_refresh_probe(
        key=_SNORT2C_CACHE_KEY,
        policy=_SNORT2C_CACHE_POLICY,
        refresh=refresh,
        stale_on_failure=True,
    )
    result.setdefault("control_path", _control_path(settings))
    result.setdefault("path", _SNORT2C_PATH)
    return result


async def reset_pfsense_security_observer_cache() -> None:
    """Reset the cached security observation for deterministic tests/debugging."""
    await reset_probe_cache(_SNORT2C_CACHE_KEY)


async def observe_pfsense_ingress_block_uncached() -> dict[str, Any]:
    """Test/debug helper that bypasses the shared cache."""
    settings = PfSenseSecuritySettings.from_environment()
    if settings is None:
        return {
            "state": "telemetry_unavailable",
            "telemetry_available": False,
            "attribution_available": False,
            "evidence": "pfSense security observer is not configured",
            "configuration": security_configuration_status(),
        }
    return await _refresh_security_observation(settings)


async def _bounded_sleep() -> None:
    """Retained only as an explicit no-op-compatible helper for legacy tests."""
    await asyncio.sleep(_PFSENSE_RETRY_DELAY_SEC)
