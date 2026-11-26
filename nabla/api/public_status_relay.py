# ruff: noqa: PLC0415, PLW0603 -- imports stay lazy to avoid cycles; relay state is process-local.
"""Signed, bounded service-state relay from TrueNAS to FastAPI Cloud.

Only a minimised, timestamped set of states crosses the trust boundary.
No caller-supplied targets or authenticated LAN data are returned to clients.
"""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from nabla.api.runtime_environment import fastapi_cloud_runtime_detected, homelab_runtime_detected
from nabla.config_settings import get_settings

PATH = "/federation/services"
HEADER = "x-nabla-federation-signature"
_DOMAIN = b"nabla:public-service-status:v1\x00"
_REDIS_KEY = "nabla:public-status:v1:latest"
MAX_BODY = 32768
# FastAPI Cloud Hobby counts awake replica-hours (180 h Nano) and always
# scales to zero; every accepted POST wakes Cloud. TrueNAS sends only at the
# owner's wake slots (one retry each); the rolling daily cap is a safety net.
WAKE_HOURS = (8, 12, 18, 21)  # Europe/Paris: morning, noon, evening, night.
_WAKE_ZONE = ZoneInfo("Europe/Paris")
# Longest silence 21:00 -> 08:00 is 11 h (12 h on the autumn DST night),
# plus a 30 min margin; afterwards states are UNKNOWN.
TTL = 45000
FRESH_SECONDS = 900  # Older relayed evidence is displayed "stale", never "fresh".
MAX_ROWS = 300  # TrueNAS confirmed 118 of 217 public services on 26/11.
_MIN_GAP = 300.0
_DAILY_SENDS = 24
_REF = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
_SIGNATURE = re.compile(r"^sha256=[0-9a-f]{64}$")
_STATES = frozenset({"ok", "warn", "fail", "scheduled", "unknown"})
_VIEW_ATTEMPTS = 4
_VIEW_RETRY_SECONDS = 30.0  # The health board refreshes in the background.
_received: dict[str, Any] | None = None
_sent_at: deque[float] = deque()
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
    return payload if _valid_rows(payload["services"]) else None


def _valid_rows(services: object) -> bool:
    if not isinstance(services, list) or not 1 <= len(services) <= MAX_ROWS:
        return False
    ids: set[str] = set()
    for row in services:
        if not isinstance(row, dict) or set(row) != {"id", "state", "age"}:
            return False
        ident = row["id"]
        if not isinstance(ident, str) or len(ident) > 128 or not _REF.fullmatch(ident) or ident in ids:
            return False
        if not isinstance(row["state"], str) or row["state"] not in _STATES or type(row["age"]) is not int or not 0 <= row["age"] < TTL:
            return False
        ids.add(ident)
    return True


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


async def read_states(revision: str) -> tuple[dict[str, str], float]:
    """Current, revision-bound, validated states and the relayed sample age in seconds."""
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
            return {}, 0.0
    else:
        data = _received
    verified = validate(data, now=datetime.now(timezone.utc))
    if verified is None or verified["catalogRevision"] != revision:
        return {}, 0.0
    # Age from the originating sample is not reset on relay/retrieval.
    elapsed = max(0, (datetime.now(timezone.utc) - _parse(verified["observed_at"])).total_seconds())
    return {row["id"]: row["state"] for row in verified["services"] if elapsed + row["age"] < TTL}, elapsed


async def _bounded_body(request: Request) -> bytes | JSONResponse:
    body = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY:
                    return _response(413, "too_large")
                body.extend(chunk)
    except TimeoutError:
        return _response(408, "body_timeout")
    return bytes(body)


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
        raw = await _bounded_body(request)
        if isinstance(raw, JSONResponse):
            return raw
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
    return _enabled() and bool(_secret()) and homelab_runtime_detected() and url == "https://fastapi-sample.fastapicloud.dev"


def public_view_rows(view: dict[str, Any], catalog: Any) -> list[dict[str, Any]]:
    """Verdicts of TrueNAS's own anonymous ``/api/ui/services``, keyed by entity name.

    That view is already public on TrueNAS (names and summarized states), so
    relaying it adds no exposure. Only a fresh live Backstage v2 board of the
    same catalog revision is relayed; ambiguous titles and UNKNOWN are dropped.
    """
    if (
        not isinstance(view, dict)
        or view.get("boardState") != "fresh"
        or view.get("catalogSource") != "backstage-v2"
        or view.get("catalogRevision") != catalog.catalogRevision
        or not isinstance(view.get("services"), list)
    ):
        return []
    entities = [entity for entity in catalog.entities if entity.kind in ("API", "Component", "Resource")]
    titles = Counter(entity.metadata.title or entity.metadata.name for entity in entities)
    names = Counter(entity.metadata.name for entity in entities)
    by_title = {
        entity.metadata.title or entity.metadata.name: entity.metadata.name
        for entity in entities
        if titles[entity.metadata.title or entity.metadata.name] == 1 and names[entity.metadata.name] == 1
    }
    rows: dict[str, dict[str, Any]] = {}
    for service in view["services"]:
        name = by_title.get(service.get("name")) if isinstance(service, dict) else None
        state = service.get("state") if isinstance(service, dict) else None
        if name and len(name) <= 128 and _REF.fullmatch(name) and state in _STATES and state != "unknown":
            # A fresh board is younger than its own TTL; the Cloud ages it from observed_at.
            rows[name] = {"id": name, "state": state, "age": 0}
    return sorted(rows.values(), key=lambda row: row["id"])[:MAX_ROWS]


def send_due(now: float) -> bool:
    """Spaced by _MIN_GAP and capped per rolling day, whatever triggers the send."""
    while _sent_at and now - _sent_at[0] >= 86400:
        _sent_at.popleft()
    return len(_sent_at) < _DAILY_SENDS and not (_sent_at and now - _sent_at[-1] < _MIN_GAP)


async def send(rows: list[dict[str, Any]], revision: str, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Sign and POST already public rows; this request is what wakes Cloud."""
    if not enabled_producer():
        return "disabled"
    if not rows:
        return "no_evidence"
    if not _REVISION.fullmatch(revision):
        return "catalog_unverified"
    now = time.monotonic()
    if not send_due(now):
        return "budget"
    _sent_at.append(now)
    data = build_payload(revision, rows, now=datetime.now(timezone.utc))
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    if len(raw) > MAX_BODY:
        return "over_budget"
    headers = {"Content-Type": "application/json", HEADER: sign(raw, _secret())}
    try:
        # Generous timeout: this POST usually meets a Cloud cold start.
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, trust_env=False, transport=transport) as client:
            response = await client.post(str(get_settings().truenas_federation_cloud_url).rstrip("/") + PATH, content=raw, headers=headers)
    except httpx.HTTPError:
        return "network_unavailable"
    return "sent" if response.status_code == 202 else f"http_{response.status_code}"


async def _local_public_view(app: Any) -> dict[str, Any] | None:
    """Read this TrueNAS app's own anonymous view in-process: no network, no port."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", timeout=60.0) as client:
        for _ in range(_VIEW_ATTEMPTS):
            response = await client.get("/api/ui/services")
            view = response.json() if response.status_code == 200 else None
            if isinstance(view, dict) and view.get("boardState") == "fresh":
                return view
            await asyncio.sleep(_VIEW_RETRY_SECONDS)
    return None


async def wake_once(app: Any) -> str:
    """One slot: read the local public view, then relay it to Cloud."""
    from nabla.api.site_architecture_catalog import fetch_site_catalog_v2

    if not enabled_producer():
        return "disabled"
    view = await _local_public_view(app)
    if view is None:
        return "view_not_fresh"
    catalog = await asyncio.wait_for(fetch_site_catalog_v2(), timeout=10.0)
    return await send(public_view_rows(view, catalog), catalog.catalogRevision)


def next_wake(now: datetime) -> datetime:
    """First wake slot strictly after ``now``, in Europe/Paris wall-clock time."""
    local = now.astimezone(_WAKE_ZONE)
    for offset in (0, 1):
        day = local.date() + timedelta(days=offset)
        for hour in WAKE_HOURS:
            slot = datetime(day.year, day.month, day.day, hour, tzinfo=_WAKE_ZONE)
            if slot > local:
                return slot
    raise AssertionError("WAKE_HOURS must not be empty")


async def run_wake_slots(app: Any) -> None:
    """TrueNAS clock: relay the local public view at each slot, retrying once.

    Gatus only probes ``/health``, which never refreshes the board, and Cloud
    has no timer: without this loop nothing would reach Cloud.
    """
    from nabla.utils.logger import logger

    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep((next_wake(now) - now).total_seconds())
        for attempt in (1, 2):
            try:
                result = await wake_once(app)
            except Exception as exc:
                result = f"error_{type(exc).__name__}"
            logger.info("public_status_relay_wake", result=result, attempt=attempt)
            if result == "sent":
                break
            await asyncio.sleep(_MIN_GAP)
