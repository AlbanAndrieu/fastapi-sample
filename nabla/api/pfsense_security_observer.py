"""Least-privilege read-only pfSense/Snort ingress-block observation."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
from typing import Any, Literal, cast

import httpx

from nabla.api.provider_credentials import inspect_environment_credentials
from nabla.api.public_egress_observer import observe_public_egress_ip
from nabla.api.truenas_transport_diagnostics import homelab_wan_metadata

ControlPathMode = Literal["shared_wan", "out_of_band"]
_CONTROL_PATH_MODES = frozenset({"shared_wan", "out_of_band"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_PFSENSE_TIMEOUT_SEC = 4.0
_TRUENAS_PUBLIC_PORT = 7000


def _security_environment_variables() -> tuple[str, str]:
    """Prefer the dedicated security identity while retaining legacy compatibility."""
    url_var = (
        "PFSENSE_SECURITY_API_URL"
        if os.getenv("PFSENSE_SECURITY_API_URL", "").strip()
        else "PFSENSE_API_URL"
    )
    key_var = (
        "PFSENSE_SECURITY_API_KEY"
        if os.getenv("PFSENSE_SECURITY_API_KEY", "").strip()
        else "PFSENSE_API_KEY"
    )
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
        """Load the dedicated security token with a temporary legacy fallback."""
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
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return exc.__class__.__name__


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
            else "Security telemetry shares the pfSense WAN path and may be blocked by the same Snort/PF decision"
        ),
    }


def _unavailable(
    settings: PfSenseSecuritySettings | None,
    evidence: str,
    *,
    blind_spot: bool | None = None,
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
    return {
        "state": "telemetry_unavailable",
        "engine": "snort",
        "firewall": "pfSense/PF",
        "mechanism": "snort2c",
        "evidence": evidence,
        "control_path": control_path,
    }


def _block_evidence(
    *,
    table: object,
    egress: dict[str, Any],
    settings: PfSenseSecuritySettings,
) -> dict[str, Any]:
    wan = homelab_wan_metadata()
    observed_ip = str(egress.get("ip") or "").strip()
    blocked = bool(observed_ip and observed_ip in _canonical_table_entries(table))
    return {
        "state": "blocked" if blocked else "clear",
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
        "evidence": (
            "Exact observed egress IP is present in pfSense table snort2c"
            if blocked
            else "Exact observed egress IP is not present in pfSense table snort2c"
        ),
        "control_path": _control_path(settings),
    }


async def observe_pfsense_ingress_block(
    *,
    settings: PfSenseSecuritySettings | None = None,
) -> dict[str, Any]:
    """Read only snort2c and attribute a block to the exact observed egress IP."""
    configured = settings or PfSenseSecuritySettings.from_environment()
    if configured is None:
        return _unavailable(None, "Dedicated pfSense security telemetry is not configured")

    egress = await observe_public_egress_ip()
    if egress.get("observed") is not True:
        return _unavailable(
            configured,
            "Runtime public egress IP could not be observed",
            blind_spot=False,
        )

    timeout = httpx.Timeout(_PFSENSE_TIMEOUT_SEC)
    try:
        async with httpx.AsyncClient(
            base_url=configured.base_url,
            headers={"X-API-Key": configured.api_key, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=False,
            verify=configured.verify_ssl,
        ) as client:
            response = await client.get("/api/v2/diagnostics/table?id=snort2c")
            response.raise_for_status()
            table = _response_data(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        reason = _safe_error(exc)
        transport_failure = isinstance(exc, httpx.TransportError)
        blind_spot = configured.control_path_mode == "shared_wan" and transport_failure
        suffix = (
            "; shared WAN control path cannot prove whether Snort blocked its own telemetry"
            if blind_spot
            else ""
        )
        return _unavailable(
            configured,
            f"snort2c telemetry unavailable: {reason}{suffix}",
            blind_spot=blind_spot,
        )

    return _block_evidence(table=table, egress=egress, settings=configured)
