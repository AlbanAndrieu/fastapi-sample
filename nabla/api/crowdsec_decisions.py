"""Owner-only, read-only list of local CrowdSec decisions (blocked IPs).

Reads the LAN-bound CrowdSec LAPI with a dedicated bouncer key, which can only
read decisions. Raw IPs never leave the homelab runtime: FastAPI Cloud cannot
reach the LAPI and returns ``not_observed``. The community blocklist (CAPI) is
not listed; only decisions made by this CrowdSec (``crowdsec``) or by hand
(``cscli``) are.
"""

from __future__ import annotations

import os
from collections import Counter
from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nabla.api.owner_ui_session import owner_ui_authenticated
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.config_settings import get_settings

_HEADERS = {"Cache-Control": "private, no-store, max-age=0", "X-Robots-Tag": "noindex, nofollow"}
_DEFAULT_LAPI_URL = "http://172.17.0.24:8084"
_ORIGINS = ("crowdsec", "cscli")
_HONEYPOT_SCENARIO_PREFIX = "nabla/honeypot"
_MAX_ROWS = 200
_MAX_BODY_BYTES = 2_000_000
_TIMEOUT_SECONDS = 3.0


def _lapi_origin() -> str | None:
    """Send the bouncer key only to a private-address LAPI origin."""
    raw = os.environ.get("CROWDSEC_LAPI_URL", _DEFAULT_LAPI_URL).strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
        private = parsed.hostname is not None and ip_address(parsed.hostname).is_private
    except ValueError:
        return None
    clean = parsed.scheme in {"http", "https"} and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment)
    return raw if private and clean else None


def _decision_row(item: object) -> dict[str, Any] | None:
    """Keep IP/range decisions only, with bounded strings; drop anything else."""
    if not isinstance(item, dict) or not isinstance(item.get("value"), str):
        return None
    try:
        ip_network(item["value"], strict=False)
    except ValueError:
        return None
    scenario = str(item.get("scenario") or "")[:160]
    return {
        "value": item["value"],
        "type": str(item.get("type") or "")[:16],
        "origin": str(item.get("origin") or "")[:16],
        "scenario": scenario,
        "duration": str(item.get("duration") or "")[:32],
        "honeypot": scenario.startswith(_HONEYPOT_SCENARIO_PREFIX),
        "simulated": item.get("simulated") is True,
    }


def _state(state: str, reason: str) -> dict[str, Any]:
    return {"state": state, "reason": reason, "source": "crowdsec_lapi", "count": 0, "honeypot_count": 0, "decisions": []}


async def fetch_crowdsec_decisions(*, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    if not homelab_runtime_detected():
        return _state("not_observed", "CrowdSec LAPI is LAN-only; open this view on the TrueNAS runtime")
    key = os.environ.get("CROWDSEC_OBSERVER_LAPI_KEY", "").strip()
    origin = _lapi_origin()
    if not key or origin is None:
        return _state("unconfigured", "Set CROWDSEC_OBSERVER_LAPI_KEY (dedicated bouncer key) and a private CROWDSEC_LAPI_URL")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = await client.get(
                f"{origin}/v1/decisions",
                params={"origins": ",".join(_ORIGINS)},
                headers={"X-Api-Key": key, "User-Agent": "fastapi-sample-crowdsec-observer/1.0"},
            )
    except httpx.TimeoutException:
        return _state("unavailable", "timeout")
    except (httpx.HTTPError, OSError):
        return _state("unavailable", "transport_error")
    if response.status_code != 200:
        return _state("unavailable", f"http_{response.status_code}")
    if len(response.content) > _MAX_BODY_BYTES:
        return _state("unavailable", "oversized_response")
    try:
        body = response.json()
    except ValueError:
        return _state("unavailable", "invalid_json")
    # LAPI answers JSON null when there is no active decision.
    if body is not None and not isinstance(body, list):
        return _state("unavailable", "unexpected_payload")
    rows = [row for row in map(_decision_row, body or []) if row is not None]
    rows.sort(key=lambda row: (not row["honeypot"], row["scenario"], row["value"]))
    return {
        "state": "ok" if rows else "empty",
        "source": "crowdsec_lapi",
        "origins": list(_ORIGINS),
        "count": len(rows),
        "honeypot_count": sum(row["honeypot"] for row in rows),
        "by_scenario": dict(Counter(row["scenario"] for row in rows).most_common(20)),
        "truncated": len(rows) > _MAX_ROWS,
        "decisions": rows[:_MAX_ROWS],
    }


def register_crowdsec_decision_routes(app: FastAPI) -> None:
    @app.get("/api/homelab/crowdsec/decisions", include_in_schema=False)
    async def crowdsec_decisions(request: Request) -> JSONResponse:
        if not owner_ui_authenticated(request, get_settings()):
            return JSONResponse({"detail": "Owner session required"}, status_code=403, headers=_HEADERS)
        if request.query_params:
            return JSONResponse({"detail": "Parameters not accepted"}, status_code=422, headers=_HEADERS)
        return JSONResponse(await fetch_crowdsec_decisions(), headers=_HEADERS)
