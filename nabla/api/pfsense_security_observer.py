"""Least-privilege read-only pfSense/Snort ingress-block observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import os
import ssl
import time
from typing import Any, Literal, cast

import httpx

from nabla.api.external_probe_cache import (
    ProbeCachePolicy,
    get_or_refresh_probe,
    reset_probe_cache,
)
from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.public_egress_observer import observe_public_egress_ip
from nabla.api.truenas_transport_diagnostics import homelab_wan_metadata

ControlPathMode = Literal["shared_wan", "out_of_band"]
_CONTROL_PATH_MODES = frozenset({"shared_wan", "out_of_band"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_PFSENSE_CONNECT_TIMEOUT_SEC = 2.0
_PFSENSE_READ_TIMEOUT_SEC = 4.0
_PFSENSE_MAX_ATTEMPTS = 1
_PFSENSE_RETRY_DELAY_SEC = 0.2
_SNORT2C_PATH = "/api/v2/diagnostics/table?id=snort2c"
_SNORT2C_CACHE_KEY = "pfsense:snort2c"
_SNORT2C_CACHE_POLICY = ProbeCachePolicy(
    success_ttl=60.0,
    failure_ttl=120.0,
    stale_ttl=600.0,
    lock_ttl=15,
)
_TRUENAS_PUBLIC_PORT = 7000


def _security_environment_variables() -> tuple[str, str]:
    """Prefer dedicated security credentials and keep explicit legacy rollback."""
    url_var = (
        "PFSENSE_SECURITY_API_URL"
        if os.getenv("PFSENSE_SECURITY_API_URL", "").strip()
        else "PFSENSE_API_URL"
    )
    if os.getenv("PFSENSE_SECURITY_API_KEY", "").strip():
        key_var = "PFSENSE_SECURITY_API_KEY"
    elif os.getenv("PFSENSE_API_KEY", "").strip():
        key_var = "PFSENSE_API_KEY"
    else:
        key_var = "PFSENSE_SECURITY_API_KEY"
    return url_var, key_var


@dataclass(frozen=True, slots=True)
class PfSenseSecuritySettings:
    """Dedicated credentials for GET-only security telemetry."""

    base_url: str
    api_key: str
    verify_ssl: bool = True
    control_path_mode: ControlPathMode = "shared_wan"

    @classmethod
    def from_environment(cls) -> PfSenseSecuritySettings | None:
        """Load the dedicated security token with an explicit legacy fallback."""
        url_var, key_var = _security_environment_variables()
        status = inspect_environment_credentials(
            "pfsense_security",
            url_var,
            key_var,
            secret_variables=frozenset({key_var}),
        )
        if not status.configured:
            return None

        raw_mode = os.getenv("PFSENSE_SECURITY_PATH_MODE", "shared_wan").strip().lower()
        mode = raw_mode if raw_mode in _CONTROL_PATH_MODES else "shared_wan"
        raw_verify = os.getenv(
            "PFSENSE_SECURITY_API_VERIFY_SSL",
            os.getenv("PFSENSE_API_VERIFY_SSL", "true"),
        ).strip().lower()
        return cls(
            base_url=os.getenv(url_var, "").strip().rstrip("/"),
            api_key=os.getenv(key_var, "").strip(),
            verify_ssl=raw_verify not in _FALSE_VALUES,
            control_path_mode=cast(ControlPathMode, mode),
        )


def security_configuration_status() -> dict[str, object]:
    """Return sanitized configuration state for the narrow Snort observer."""
    url_var, key_var = _security_environment_variables()
    status = inspect_environment_credentials(
        "pfsense_security",
        url_var,
        key_var,
        secret_variables=frozenset({key_var}),
    ).as_dict()
    status["required_privilege"] = "api-v2-diagnostics-table-get"
    status["write_privileges_required"] = False
    status["credential_mode"] = (
        "dedicated_security"
        if key_var == "PFSENSE_SECURITY_API_KEY"
        else "legacy_shared"
    )
    return status


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return (str(exc).strip() or exc.__class__.__name__)[:240]


def _error_kind(exc: BaseException) -> str:
    message = str(exc).casefold()
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        if any(marker in message for marker in ("certificate", "ssl", "tls")):
            return "tls_error"
        return "connect_error"
    if isinstance(exc, ssl.SSLError) or any(
        marker in message for marker in ("certificate", "ssl", "tls")
    ):
        return "tls_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "unknown_error"


def _failure_stage(error_kind: str) -> str:
    if error_kind in {"connect_timeout", "connect_error", "tls_error", "os_error"}:
        return "connect"
    if error_kind == "pool_timeout":
        return "client_pool"
    if error_kind == "read_timeout":
        return "response"
    if error_kind.startswith("http_"):
        return "http_response"
    return "request"


def _response_data(payload: object) -> object:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _canonical_table_entries(table: object) -> frozenset[str]:
    candidate: object = table
    if isinstance(table, list):
        matching = [
            row
            for row in table
            if isinstance(row, dict) and str(row.get("name") or "") == "snort2c"
        ]
        candidate = matching[0] if matching else None
    if isinstance(candidate, dict):
        candidate = candidate.get("entries")

    if isinstance(candidate, str):
        raw_entries = candidate.split()
    elif isinstance(candidate, list):
        raw_entries = [str(value).strip() for value in candidate]
    else:
        raw_entries = []

    normalized: set[str] = set()
    for raw in raw_entries:
        try:
            normalized.add(str(ipaddress.ip_address(raw)))
        except ValueError:
            continue
    return frozenset(normalized)


def _sanitized_table(table: object) -> dict[str, Any]:
    """Persist only canonical IP entries, never the raw pfREST response."""
    return {
        "name": "snort2c",
        "entries": sorted(_canonical_table_entries(table)),
    }


def _control_path(
    settings: PfSenseSecuritySettings,
    *,
    blind_spot: bool | None = None,
) -> dict[str, Any]:
    independent = settings.control_path_mode == "out_of_band"
    effective_blind_spot = not independent if blind_spot is None else blind_spot
    return {
        "mode": settings.control_path_mode,
        "independent_from_wan_filter": independent,
        "blind_spot": effective_blind_spot,
        "detail": (
            "Out-of-band pfSense telemetry path is independent from the public WAN listener"
            if independent
            else "Security telemetry shares the pfSense WAN path and is not an independent control channel"
        ),
    }


def _with_telemetry(
    result: dict[str, Any],
    telemetry: dict[str, Any] | None,
) -> dict[str, Any]:
    return {**result, **(telemetry or {})}


def _unavailable(
    settings: PfSenseSecuritySettings | None,
    evidence: str,
    *,
    blind_spot: bool | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control_path = (
        _control_path(settings, blind_spot=blind_spot)
        if settings is not None
        else {
            "mode": "unconfigured",
            "independent_from_wan_filter": False,
            "blind_spot": False,
            "detail": "Dedicated pfSense security telemetry is not configured",
        }
    )
    return _with_telemetry(
        {
            "state": "telemetry_unavailable",
            "telemetry_available": False,
            "attribution_available": False,
            "engine": "snort",
            "firewall": "pfSense/PF",
            "mechanism": "snort2c",
            "evidence": evidence,
            "control_path": control_path,
        },
        telemetry,
    )


def _attribution_unavailable(
    *,
    table: object,
    settings: PfSenseSecuritySettings,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wan = homelab_wan_metadata()
    return _with_telemetry(
        {
            "state": "attribution_unavailable",
            "telemetry_available": True,
            "attribution_available": False,
            "engine": "snort",
            "firewall": "pfSense/PF",
            "mechanism": "snort2c",
            "source": {"ip": None, "role": "FastAPI Cloud egress (not observed)"},
            "destination": {
                "ip": wan["ipv4"],
                "port": _TRUENAS_PUBLIC_PORT,
                "role": "pfSense WAN / homelab public endpoint",
            },
            "table_entry_count": len(_canonical_table_entries(table)),
            "evidence": (
                "snort2c telemetry is reachable, but the runtime public egress IP could not be observed"
            ),
            "control_path": _control_path(settings, blind_spot=False),
        },
        telemetry,
    )


def _block_evidence(
    *,
    table: object,
    egress: dict[str, Any],
    settings: PfSenseSecuritySettings,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wan = homelab_wan_metadata()
    observed_ip = str(egress.get("ip") or "").strip()
    blocked = bool(observed_ip and observed_ip in _canonical_table_entries(table))
    return _with_telemetry(
        {
            "state": "blocked" if blocked else "clear",
            "telemetry_available": True,
            "attribution_available": True,
            "engine": "snort",
            "firewall": "pfSense/PF",
            "mechanism": "snort2c",
            "source": {
                "ip": observed_ip or None,
                "role": "FastAPI Cloud egress (observed)",
            },
            "destination": {
                "ip": wan["ipv4"],
                "port": _TRUENAS_PUBLIC_PORT,
                "role": "pfSense WAN / homelab public endpoint",
            },
            "table_entry_count": len(_canonical_table_entries(table)),
            "evidence": (
                "Exact observed egress IP is present in pfSense table snort2c"
                if blocked
                else "Exact observed egress IP is not present in pfSense table snort2c"
            ),
            "control_path": _control_path(settings),
        },
        telemetry,
    )


def _stale_telemetry(
    *,
    table: object,
    egress: dict[str, Any],
    settings: PfSenseSecuritySettings,
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    wan = homelab_wan_metadata()
    observed_ip = str(egress.get("ip") or "").strip()
    return _with_telemetry(
        {
            "state": "telemetry_stale",
            "telemetry_available": True,
            "attribution_available": False,
            "engine": "snort",
            "firewall": "pfSense/PF",
            "mechanism": "snort2c",
            "source": {
                "ip": observed_ip or None,
                "role": "FastAPI Cloud egress (observed)",
            },
            "destination": {
                "ip": wan["ipv4"],
                "port": _TRUENAS_PUBLIC_PORT,
                "role": "pfSense WAN / homelab public endpoint",
            },
            "table_entry_count": len(_canonical_table_entries(table)),
            "last_known_match": bool(
                observed_ip and observed_ip in _canonical_table_entries(table)
            ),
            "evidence": (
                "Last-known-good snort2c table retained after refresh failure; current block attribution is intentionally withheld"
            ),
            "control_path": _control_path(settings, blind_spot=False),
        },
        telemetry,
    )


async def _fetch_snort2c(
    settings: PfSenseSecuritySettings,
) -> tuple[object | None, dict[str, Any]]:
    timeout = httpx.Timeout(
        connect=_PFSENSE_CONNECT_TIMEOUT_SEC,
        read=_PFSENSE_READ_TIMEOUT_SEC,
        write=_PFSENSE_CONNECT_TIMEOUT_SEC,
        pool=_PFSENSE_CONNECT_TIMEOUT_SEC,
    )
    started = time.monotonic()
    last_error: BaseException | None = None
    attempts = 0
    async with httpx.AsyncClient(
        base_url=settings.base_url,
        headers={"X-API-Key": settings.api_key, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
        verify=settings.verify_ssl,
    ) as client:
        for attempt in range(1, _PFSENSE_MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                response = await client.get(_SNORT2C_PATH)
                response.raise_for_status()
                return _sanitized_table(_response_data(response.json())), {
                    "path": _SNORT2C_PATH,
                    "attempts": attempt,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "http_status": response.status_code,
                }
            except (httpx.HTTPError, OSError, ValueError) as exc:
                last_error = exc
                kind = _error_kind(exc)
                retryable = kind in {
                    "connect_timeout",
                    "read_timeout",
                    "pool_timeout",
                    "timeout",
                    "connect_error",
                    "os_error",
                }
                if attempt < _PFSENSE_MAX_ATTEMPTS and retryable:
                    await asyncio.sleep(_PFSENSE_RETRY_DELAY_SEC)
                    continue
                break

    error = last_error or RuntimeError("snort2c request failed")
    kind = _error_kind(error)
    return None, {
        "path": _SNORT2C_PATH,
        "attempts": attempts,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "error_kind": kind,
        "failure_stage": _failure_stage(kind),
        "exception_type": type(error).__name__,
        "refresh_error": _safe_error(error),
    }


async def _snort2c_loader(settings: PfSenseSecuritySettings) -> dict[str, Any]:
    table, telemetry = await _fetch_snort2c(settings)
    return {
        "ok": table is not None,
        "table": table,
        "telemetry": telemetry,
    }


async def _read_snort2c_cached(
    settings: PfSenseSecuritySettings,
) -> tuple[object | None, dict[str, Any]]:
    cached = await get_or_refresh_probe(
        _SNORT2C_CACHE_KEY,
        lambda: _snort2c_loader(settings),
        is_success=lambda value: value.get("ok") is True,
        policy=_SNORT2C_CACHE_POLICY,
    )
    value = cached.value
    telemetry = dict(value.get("telemetry") or {})
    telemetry.update(cached.metadata)

    if cached.metadata.get("stale") is True:
        good = cached.last_good or value
        table = good.get("table") if isinstance(good, dict) else None
        telemetry["cached"] = True
        telemetry.setdefault("refresh_error", "snort2c refresh is in progress")
        return table, telemetry

    if value.get("ok") is True:
        return value.get("table"), telemetry

    if cached.last_good is not None:
        table = cached.last_good.get("table")
        telemetry["stale"] = True
        telemetry["cached"] = True
        return table, telemetry
    return None, telemetry


async def observe_pfsense_ingress_block(
    *,
    settings: PfSenseSecuritySettings | None = None,
) -> dict[str, Any]:
    """Read snort2c and attribute only fresh evidence to the exact egress IP."""
    configured = settings or PfSenseSecuritySettings.from_environment()
    if configured is None:
        return _unavailable(None, "Dedicated pfSense security telemetry is not configured")

    table_result, egress_result = await asyncio.gather(
        _read_snort2c_cached(configured),
        observe_public_egress_ip(),
    )
    table, telemetry = table_result
    if table is None:
        blind_spot = configured.control_path_mode == "shared_wan" and telemetry.get(
            "failure_stage"
        ) in {"connect", "response", "request", "client_pool"}
        suffix = (
            "; shared WAN control path cannot prove whether the telemetry request itself was filtered"
            if blind_spot
            else ""
        )
        return _unavailable(
            configured,
            f"snort2c telemetry unavailable: {telemetry.get('refresh_error', 'request failed')}{suffix}",
            blind_spot=blind_spot,
            telemetry=telemetry,
        )

    egress = egress_result if isinstance(egress_result, dict) else {}
    if telemetry.get("stale") is True:
        return _stale_telemetry(
            table=table,
            egress=egress,
            settings=configured,
            telemetry=telemetry,
        )
    if egress.get("observed") is not True:
        return _attribution_unavailable(
            table=table,
            settings=configured,
            telemetry=telemetry,
        )
    return _block_evidence(
        table=table,
        egress=egress,
        settings=configured,
        telemetry=telemetry,
    )


async def reset_snort2c_cache() -> None:
    """Reset process-local Snort probe state for deterministic tests."""
    await reset_probe_cache(_SNORT2C_CACHE_KEY)
