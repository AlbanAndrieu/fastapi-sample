"""Bounded read-only Freebox OS discovery check, only from the homelab LAN.

Authentication-free /api_version confirms API transport, not WAN connectivity,
routing, DHCP, firmware security or the Freebox administration login.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx

from nabla.api.edge_provider import active_edge_provider
from nabla.api.runtime_environment import known_paas_runtime_detected


def _allowed_origin(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname == "192.168.1.254"
        and parsed.port in {None, 80}
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


async def check_freebox_api(*, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """GET only /api_version; no Freebox app_token or session in this probe."""
    base: dict[str, Any] = {
        "probe": "freebox_api_version",
        "credential_mode": "anonymous_discovery",
        "vantage_point": "fastapi_cloud" if known_paas_runtime_detected() else "homelab",
    }
    if active_edge_provider() != "freebox":
        return {**base, "skipped": True, "reachable": None, "status_confirmed": False, "state": "unknown", "reason": "Freebox is not the selected network edge"}
    if known_paas_runtime_detected():
        return {**base, "skipped": True, "reachable": None, "status_confirmed": False, "state": "unknown", "reason": "Freebox LAN probe belongs to the TrueNAS observer, not FastAPI Cloud"}

    origin = os.environ.get("FREEBOX_BASE_URL", "http://192.168.1.254").rstrip("/")
    if not _allowed_origin(origin):
        return {**base, "skipped": True, "reachable": None, "status_confirmed": False, "state": "unknown", "reason": "Freebox origin is not the approved local router address"}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.get(
                origin + "/api_version",
                headers={"User-Agent": "fastapi-sample-freebox-observer/1.0"},
            )
        if response.status_code != 200:
            return {**base, "reachable": True, "status_confirmed": True, "state": "warn", "http_status": response.status_code}
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("api_version"), str):
            return {**base, "reachable": True, "status_confirmed": False, "state": "unknown", "reason": "Freebox response is not a version discovery document"}
        return {**base, "reachable": True, "status_confirmed": True, "state": "ok", "api_version": body["api_version"]}
    except (httpx.HTTPError, OSError, ValueError):
        return {**base, "reachable": None, "status_confirmed": False, "state": "unknown", "reason": "Freebox discovery could not be confirmed from this runtime"}
