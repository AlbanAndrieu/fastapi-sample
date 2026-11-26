"""Signed, bounded service-state relay from TrueNAS to FastAPI Cloud.

Only a minimised, timestamped set of states crosses the trust boundary.
No caller-supplied targets or authenticated LAN data are returned to clients.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from nabla.api.runtime_environment import fastapi_cloud_runtime_detected, homelab_runtime_detected
from nabla.config_settings import get_settings

PATH = "/federation/services"
HEADER = "x-nabla-federation-signature"
_DOMAIN = b"nabla:public-service-status:v1\x00"
_REDIS_KEY = "nabla:public-status:v1:latest"
MAX_BODY = 16384
TTL = 600
MAX_ROWS = 120
_INTERVAL = 90.0
_REF = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
_SIGNATURE = re.compile(r"^sha256=[0-9a-f]{64}$")
_STATES = frozenset({"ok", "warn", "fail", "scheduled", "unknown"})
_received: dict[str, Any] | None = None
_next_push = 0.0
_pending: set[asyncio.Task[str]] = set()
_RESPONSE_HEADERS = {"Cache-Control": "private, no-store"}


def _enabled() -> bool:
    return os.getenv("TRUENAS_SERVICE_STATUS_RELAY_ENABLED", "").strip().lower() == "true"


def _secret() -> str:
    configured = getattr(get_settings(), "truenas_federation_secret", None)
    value = configured.get_secret_value() if configured is not None else ""
    return value if isinstance(value, str) and len(value) >= 32 else ""


def sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), _DOMAIN + raw, hashlib.sha256).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def project_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Only proven non-stale probe rows. Prefer LAN over blocked WAN Access."""
    collected: dict[str, dict[str, Any]] = {}
    for scope in ("services", "internal_services"):
        for row in payload.get(scope, []):
            if not isinstance(row, dict) or row.get("probe_stale") is True or row.get("timed_out") is True:
                continue
            service_id = row.get("id")
            state = row.get("effective_state") or row.get("state")
            age = row.get("probe_age_seconds")
            stale_after = row.get("probe_stale_after_seconds")
            if (
                not isinstance(service_id, str) or len(service_id) > 128 or not _REF.fullmatch(service_id)
                or state not in _STATES or state == "unknown"
                or row.get("probe_source") not in {"origin", "memory"}
                or not isinstance(age, (int, float)) or isinstance(age, bool) or not math.isfinite(age)
                or not isinstance(stale_after, (int, float)) or isinstance(stale_after, bool) or not math.isfinite(stale_after)
                or age < 0 or stale_after <= age
            ):
                continue
            # Cloud never sees internal endpoints, probe text, device IDs or IPs.
            item = {"id": service_id, "state": state, "age": min(599, int(age))}
            # Internal TCP is a useful LAN reachability hint, not app health;
            # its state can override an Access-challenged public observation.
            collected[service_id] = item
    return sorted(collected.values(), key=lambda item: item["id"])[:MAX_ROWS]


def build_payload(revision: str, rows: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    return {
        "v": 1,
        "catalogRevision": revision,
        "observed_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=TTL)),
        "nonce": secrets.token_hex(16),
        "services": rows[:MAX_ROWS],
    }


def validate(payload: object, *, now: datetime) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or set(payload) != {"v", "catalogRevision", "observed_at", "expires_at", "nonce", "services"}:
        return None
    if type(payload["v"]) is not int or payload["v"] != 1 or not isinstance(payload["catalogRevision"], str) or not _REVISION.fullmatch(payload["catalogRevision"]):
        return None
    observed, expiry = _parse(payload["observed_at"]), _parse(payload["expires_at"])
    if observed is None or expiry is None or observed > now + timedelta(seconds=60) or observed < now - timedelta(seconds=TTL):
        return None
    if not now < expiry or not timedelta(seconds=0) < expiry - observed <= timedelta(seconds=TTL):
        return None
    if not isinstance(payload["nonce"], str) or not re.fullmatch(r"[a-f0-9]{32}", payload["nonce"]):
        return None
    services = payload["services"]
    if not isinstance(services, list) or not 1 <= len(services) <= MAX_ROWS:
        return None
    ids: set[str] = set()
    for row in services:
        if not isinstance(row, dict) or set(row) != {"id", "state", "age"}:
            return None
        ident = row["id"]
        if not isinstance(ident, str) or len(ident) > 128 or not _REF.fullmatch(ident) or ident in ids:
            return None
        if not isinstance(row["state"], str) or row["state"] not in _STATES or type(row["age"]) is not int or not 0 <= row["age"] < TTL:
            return None
        ids.add(ident)
    return payload


def _response(status: int, code: str) -> JSONResponse:
    return JSONResponse({"state": code}, status_code=status, headers=_RESPONSE_HEADERS)


async def _redis() -> Any | None:
    if not os.getenv("REDIS_URL", "").strip():
        return None
    try:
        from nabla.api.external_probe_cache_redis import resolve_redis_client
        return resolve_redis_client()
    except (ImportError, RuntimeError):
        return None


# Compares epoch-free canonical fixed-second UTC strings lexicographically.
_CAS = """
local old = redis.call('GET', KEYS[1])
if old and cjson.decode(old).observed_at >= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""


async def _save(data: dict[str, Any]) -> bool:
    """Atomic shared latest-wins on Redis, memory fallback for one replica."""
    global _received
    redis = await _redis()
    if redis is not None:
        try:
            accepted = await asyncio.wait_for(
                redis.eval(_CAS, 1, _REDIS_KEY, data["observed_at"], json.dumps(data, separators=(",", ":")), TTL),
                timeout=0.5,
            )
            return accepted == 1
        except Exception:
            # No permissive fallback when shared state could be inconsistent.
            return False
    if _received is not None and _received["observed_at"] >= data["observed_at"]:
        return False
    _received = data
    return True


async def read_states(revision: str) -> dict[str, str]:
    """Read only current, revision-bound, validated states."""
    data = None
    redis = await _redis()
    if redis is not None:
        try:
            raw = await asyncio.wait_for(redis.get(_REDIS_KEY), timeout=0.15)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if isinstance(raw, str) and len(raw) <= MAX_BODY:
                data = json.loads(raw)
        except Exception:
            return {}
    else:
        data = _received
    verified = validate(data, now=datetime.now(timezone.utc))
    if verified is None or verified["catalogRevision"] != revision:
        return {}
    # Age from the originating sample is not reset on relay/retrieval.
    elapsed = max(0, (datetime.now(timezone.utc) - _parse(verified["observed_at"])).total_seconds())
    return {row["id"]: row["state"] for row in verified["services"] if elapsed + row["age"] < TTL}


def register_routes(app: FastAPI) -> None:
    @app.post(PATH, include_in_schema=False)
    async def receive(request: Request) -> JSONResponse:
        if not _enabled() or not _secret() or not fastapi_cloud_runtime_detected(request.url.hostname):
            return _response(404, "disabled")
        signatures = request.headers.getlist(HEADER)
        if len(signatures) != 1 or not _SIGNATURE.fullmatch(signatures[0]):
            return _response(401, "signature_required")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return _response(415, "json_required")
        body = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY:
                        return _response(413, "too_large")
                    body.extend(chunk)
        except TimeoutError:
            return _response(408, "body_timeout")
        raw = bytes(body)
        if not hmac.compare_digest(sign(raw, _secret()), signatures[0]):
            return _response(401, "bad_signature")
        try:
            data = validate(json.loads(raw), now=datetime.now(timezone.utc))
        except (ValueError, UnicodeError, RecursionError):
            return _response(400, "invalid_json")
        if data is None:
            return _response(422, "invalid_payload")
        if not await _save(data):
            return _response(409, "stale_or_storage_unavailable")
        return _response(202, "accepted")


def enabled_producer() -> bool:
    url = str(getattr(get_settings(), "truenas_federation_cloud_url", "") or "").rstrip("/")
    return (
        _enabled() and bool(_secret()) and homelab_runtime_detected()
        and url == "https://fastapi-sample.fastapicloud.dev"
    )


async def push(payload: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Push sanitised results from an already executed homelab probe; no new LAN I/O."""
    from nabla.api.site_architecture_catalog import fetch_catalog_v2_source

    if not enabled_producer():
        return "disabled"
    rows = project_rows(payload)
    if not rows:
        return "no_evidence"
    try:
        source = await asyncio.wait_for(fetch_catalog_v2_source(), timeout=1.0)
    except Exception:
        return "catalog_unavailable"
    revision = source.get("catalogRevision")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        return "catalog_unverified"
    data = build_payload(revision, rows, now=datetime.now(timezone.utc))
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    if len(raw) > MAX_BODY:
        return "over_budget"
    headers = {"Content-Type": "application/json", HEADER: sign(raw, _secret())}
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = await client.post(str(get_settings().truenas_federation_cloud_url).rstrip("/") + PATH, content=raw, headers=headers)
    except httpx.HTTPError:
        return "network_unavailable"
    return "sent" if response.status_code == 202 else f"http_{response.status_code}"


def schedule(payload: dict[str, Any]) -> None:
    """At most one push per 90 s during existing TrueNAS health collection."""
    global _next_push
    if not enabled_producer() or time.monotonic() < _next_push:
        return
    _next_push = time.monotonic() + _INTERVAL
    task = asyncio.create_task(push(payload), name="truenas-public-status-relay")
    _pending.add(task)
    task.add_done_callback(_pending.discard)
