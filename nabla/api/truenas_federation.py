"""Signed TrueNAS to FastAPI Cloud evidence relay (P2 federation, 22/11 residual).

Off by default: without ``TRUENAS_FEDERATION_SECRET`` (at least 32 characters)
the Cloud route answers 404 and TrueNAS sends nothing. TrueNAS pushes; Cloud
never reaches the LAN. The aggregate is a closed enumeration (no host, IP,
error text or secret), dated, bounded by a short TTL and signed over its raw
bytes with a domain-separated HMAC. Relayed evidence is never a current verdict.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from nabla.api.runtime_environment import fastapi_cloud_runtime_detected, homelab_runtime_detected
from nabla.config_settings import get_settings

PATH = "/federation/truenas"
SIGNATURE_HEADER = "x-nabla-federation-signature"
MAX_BODY = 2048
TTL_SECONDS = 600
MAX_TTL_SECONDS = 900
MAX_SKEW_SECONDS = 60
PUSH_INTERVAL_SECONDS = 60
_DOMAIN = b"nabla:truenas-federation:v1\x00"
_KEYS = frozenset({"v", "source", "vantage", "observed_at", "expires_at", "truenas_api", "stage", "nonce"})
_STAGE = re.compile(r"[a-z][a-z0-9_]{0,39}")
_SIGNATURE = re.compile(r"sha256=[0-9a-f]{64}")
_HEADERS = {"Cache-Control": "private, no-store"}
# shortcut: last record per Cloud worker in memory; move to a namespaced Redis key once Cloud has one.
_received: dict[str, dict[str, Any]] = {}
_push_state = {"last": 0.0}
_push_tasks: set[asyncio.Task[str]] = set()


def _secret() -> str:
    value = getattr(get_settings(), "truenas_federation_secret", None)
    secret = value.get_secret_value() if value is not None else ""
    return secret if len(secret) >= 32 else ""


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return None


def sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), _DOMAIN + raw, hashlib.sha256).hexdigest()


def build_aggregate(api_result: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Minimize one TrueNAS API observation to closed values."""
    reachable = api_result.get("reachable")
    stage = str(api_result.get("stage") or "unknown")
    return {
        "v": 1,
        "source": "truenas",
        "vantage": "homelab_lan",
        "observed_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=TTL_SECONDS)),
        "truenas_api": "ok" if reachable is True else "fail" if reachable is False else "unknown",
        "stage": stage if _STAGE.fullmatch(stage) else "other",
        "nonce": secrets.token_hex(8),
    }


def validate_aggregate(payload: object, *, now: datetime) -> dict[str, Any] | None:
    """Accept only the exact closed schema, a bounded TTL and a non-future timestamp."""
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        return None
    if (payload["v"], payload["source"], payload["vantage"]) != (1, "truenas", "homelab_lan"):
        return None
    if payload["truenas_api"] not in {"ok", "fail", "unknown"}:
        return None
    if not isinstance(payload["stage"], str) or not _STAGE.fullmatch(payload["stage"]):
        return None
    if not isinstance(payload["nonce"], str) or not re.fullmatch(r"[0-9a-f]{16}", payload["nonce"]):
        return None
    observed, expires = _parse(payload["observed_at"]), _parse(payload["expires_at"])
    if observed is None or expires is None or observed > now + timedelta(seconds=MAX_SKEW_SECONDS):
        return None
    if not now < expires or not timedelta(0) < expires - observed <= timedelta(seconds=MAX_TTL_SECONDS):
        return None
    return dict(payload)


def relayed_truenas_evidence(now: datetime | None = None) -> dict[str, Any] | None:
    """Last relayed record while its TTL holds; absent evidence stays ``None``."""
    record = _received.get("truenas")
    now = now or datetime.now(timezone.utc)
    if record is None or (_parse(record["expires_at"]) or now) <= now:
        return None
    observed = _parse(record["observed_at"]) or now
    return {
        "source": "truenas_lan_relay",
        "vantage": record["vantage"],
        "truenas_api": record["truenas_api"],
        "stage": record["stage"],
        "observed_at": record["observed_at"],
        "expires_at": record["expires_at"],
        "age_seconds": max(0, round((now - observed).total_seconds())),
    }


def _response(status: int, code: str) -> JSONResponse:
    return JSONResponse({"state": code}, status_code=status, headers=_HEADERS)


async def _bounded_body(request: Request) -> bytes | None:
    body = bytearray()
    async with asyncio.timeout(5):
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                return None
            body.extend(chunk)
    return bytes(body)


def _header_denial(request: Request) -> JSONResponse | None:
    signatures = request.headers.getlist(SIGNATURE_HEADER)
    if len(signatures) != 1 or not _SIGNATURE.fullmatch(signatures[0]):
        return _response(401, "signature_required")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return _response(415, "json_required")
    return None


def register_truenas_federation_routes(app: FastAPI) -> None:
    from nabla.api.public_status_relay import register_routes as register_status_routes

    register_status_routes(app)
    @app.post(PATH, include_in_schema=False)
    async def receive(request: Request) -> JSONResponse:
        secret = _secret()
        if not secret or not fastapi_cloud_runtime_detected(request.url.hostname):
            return _response(404, "disabled")
        denied = _header_denial(request)
        if denied is not None:
            return denied
        signature = request.headers[SIGNATURE_HEADER]
        try:
            raw = await _bounded_body(request)
        except TimeoutError:
            return _response(408, "body_timeout")
        if raw is None:
            return _response(413, "too_large")
        if not hmac.compare_digest(sign(raw, secret), signature):
            return _response(401, "invalid_signature")
        try:
            record = validate_aggregate(json.loads(raw), now=datetime.now(timezone.utc))
        except (ValueError, UnicodeError, RecursionError):
            return _response(400, "invalid_json")
        if record is None:
            return _response(422, "invalid_aggregate")
        previous = _received.get("truenas")
        # Signed but older or equal observations are replays: never roll evidence back.
        if previous is not None and previous["observed_at"] >= record["observed_at"]:  # same validated ISO-8601 Z format
            return _response(409, "stale")
        _received["truenas"] = record
        return _response(202, "accepted")


def push_enabled() -> bool:
    url = str(getattr(get_settings(), "truenas_federation_cloud_url", "") or "")
    return homelab_runtime_detected() and url.startswith("https://") and bool(_secret())


async def push_truenas_aggregate(api_result: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Send one signed aggregate at most every PUSH_INTERVAL_SECONDS; failures are only reported."""
    if not push_enabled():
        return "disabled"
    started = time.monotonic()
    if started - _push_state["last"] < PUSH_INTERVAL_SECONDS:
        return "throttled"
    _push_state["last"] = started
    url = str(get_settings().truenas_federation_cloud_url).rstrip("/") + PATH
    raw = json.dumps(build_aggregate(api_result, now=datetime.now(timezone.utc)), separators=(",", ":"), sort_keys=True).encode()
    headers = {"content-type": "application/json", SIGNATURE_HEADER: sign(raw, _secret())}
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = await client.post(url, content=raw, headers=headers)
    except httpx.HTTPError as exc:
        return exc.__class__.__name__
    return "sent" if response.status_code == 202 else f"http_{response.status_code}"


def schedule_truenas_push(api_result: dict[str, Any]) -> None:
    """Fire-and-forget from the TrueNAS probe path; never delays the health snapshot."""
    if push_enabled():
        task = asyncio.create_task(push_truenas_aggregate(api_result))
        _push_tasks.add(task)
        task.add_done_callback(_push_tasks.discard)
