"""Published RSS relevance decisions, not raw articles, on the FastAPI Cloud edge.

TrueNAS classifies a bounded subset using its private FreshRSS/Langfuse/LiteLLM
identity, then explicitly pushes only opaque IDs and matched technology tags.
Cloud stores those decisions in shared Redis; the site joins them to its own
independently allowlisted FreshRSS subscriptions. Nothing triggers inference
on anonymous requests or exposes the GReader credential or model prompt.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
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

INGEST_PATH = "/federation/rss"
PUBLIC_PATH = "/api/site/rss/v1"
SIGNATURE_HEADER = "x-nabla-rss-signature"
_DOMAIN = b"nabla:rss-relevance-publication:v1\x00"
_CACHE_KEY = "nabla:rss-relevance:v1:current"
MAX_BODY_BYTES = 8192
MAX_BATCH = 5
MAX_PUBLISHED = 150
MAX_ITEM_AGE_SECONDS = 86400
MAX_CLOCK_SKEW_SECONDS = 60
_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[0-9a-f]{64}$")
_TAG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_SIGNATURE = re.compile(r"^sha256=[0-9a-f]{64}$")
_NOCACHE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}

# Redis EVAL atomically rejects out-of-order batches, merges only decisions
# from the same catalog revision and managed prompt version and limits memory.
_CAS = """
local now = tonumber(ARGV[2])
local incoming = cjson.decode(ARGV[1])
local previous = redis.call('GET', KEYS[1])
local merged = {}
if previous then
    local old = cjson.decode(previous)
    if old.observed_at >= incoming.observed_at then return 0 end
    if old.catalogRevision == incoming.catalogRevision and
       old.promptVersion == incoming.promptVersion then
        for _, item in ipairs(old.items) do
            if now - item.seen_at < 86400 and item.seen_at <= now + 60 then
                merged[item.article_id] = item
            end
        end
    end
end
for _, item in ipairs(incoming.items) do
    merged[item.article_id] = {article_id=item.article_id,
                               matched=item.matched, seen_at=now}
end
local selected = {}
for _, item in pairs(merged) do table.insert(selected, item) end
table.sort(selected, function(a,b)
    if a.seen_at == b.seen_at then return a.article_id < b.article_id end
    return a.seen_at > b.seen_at
end)
local bounded = {}
for i=1,math.min(#selected, 150) do bounded[i] = selected[i] end
incoming.items = bounded
redis.call('SET', KEYS[1], cjson.encode(incoming), 'EX', 86400)
return 1
"""


def publication_enabled() -> bool:
    return os.getenv("RSS_RELEVANCE_PUBLICATION_ENABLED", "").strip().lower() == "true"


def _secret() -> str:
    configured = getattr(get_settings(), "truenas_federation_secret", None)
    value = configured.get_secret_value() if configured is not None else ""
    return value if isinstance(value, str) and len(value) >= 32 else ""


def sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), _DOMAIN + raw, hashlib.sha256).hexdigest()


def validate_batch(value: object, *, now: int | None = None) -> dict[str, Any] | None:
    """Closed wire contract; reject titles, descriptions, URLs and arbitrary keys."""
    now = int(time.time()) if now is None else now
    if not isinstance(value, dict) or set(value) != {
        "v", "catalogRevision", "promptVersion", "observed_at", "nonce", "items"
    }:
        return None
    if type(value["v"]) is not int or value["v"] != 1:
        return None
    if not isinstance(value["catalogRevision"], str) or not _REVISION.fullmatch(value["catalogRevision"]):
        return None
    if type(value["promptVersion"]) is not int or not 1 <= value["promptVersion"] <= 1_000_000:
        return None
    observed = value["observed_at"]
    if type(observed) is not int or not now - 300 <= observed <= now + MAX_CLOCK_SKEW_SECONDS:
        return None
    if not isinstance(value["nonce"], str) or not re.fullmatch(r"[a-f0-9]{32}", value["nonce"]):
        return None
    items = value["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH:
        return None
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"article_id", "matched"}:
            return None
        identity = item["article_id"]
        matched = item["matched"]
        if not isinstance(identity, str) or not _ID.fullmatch(identity) or identity in seen:
            return None
        if not isinstance(matched, list) or not 1 <= len(matched) <= 8:
            return None
        if not all(isinstance(tag, str) and _TAG.fullmatch(tag) for tag in matched):
            return None
        if len(set(matched)) != len(matched):
            return None
        seen.add(identity)
    return value


def build_batch(rows: list[dict[str, Any]], *, now: int | None = None) -> dict[str, Any]:
    """Take verified LiteLLM decisions; omit article titles, model reasoning and content."""
    now = int(time.time()) if now is None else now
    if len(rows) > MAX_BATCH:
        raise ValueError("Too many RSS decisions")
    if not rows:
        raise ValueError("No RSS decisions to publish")
    revisions = {row.get("catalogRevision") for row in rows}
    versions = {row.get("prompt_version") for row in rows}
    if len(revisions) != 1 or len(versions) != 1:
        raise ValueError("Mixed catalog or prompt revisions")
    items = [
        {"article_id": row["article_id"], "matched": sorted(set(row["matched"]))[:8]}
        for row in rows
    ]
    batch = {
        "v": 1,
        "catalogRevision": next(iter(revisions)),
        "promptVersion": next(iter(versions)),
        "observed_at": now,
        "nonce": secrets.token_hex(16),
        "items": items,
    }
    if validate_batch(batch, now=now) is None:
        raise ValueError("Unverified RSS decisions")
    return batch


def _safe_record(value: object, *, now: int) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != {
        "v", "catalogRevision", "promptVersion", "observed_at", "nonce", "items"
    }:
        return None
    if (
        value["v"] != 1 or type(value["promptVersion"]) is not int
        or not isinstance(value["catalogRevision"], str) or not _REVISION.fullmatch(value["catalogRevision"])
        or type(value["observed_at"]) is not int or value["observed_at"] > now + 60
        or not isinstance(value["items"], list) or len(value["items"]) > MAX_PUBLISHED
    ):
        return None
    items = []
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) != {"article_id", "matched", "seen_at"}:
            return None
        age = item["seen_at"]
        if type(age) is not int or age > now + 60:
            return None
        if not isinstance(item["article_id"], str) or not _ID.fullmatch(item["article_id"]):
            return None
        matched = item["matched"]
        if not isinstance(matched, list) or not 1 <= len(matched) <= 8:
            return None
        if not all(isinstance(tag, str) and _TAG.fullmatch(tag) for tag in matched):
            return None
        if now - age < MAX_ITEM_AGE_SECONDS:
            items.append({"article_id": item["article_id"], "matched": matched})
    return {
        "schemaVersion": 1,
        "model": "rss-relevance",
        "catalogRevision": value["catalogRevision"],
        "promptVersion": value["promptVersion"],
        "items": items,
    }


def _redis() -> Any | None:
    if not os.getenv("REDIS_URL", "").strip():
        return None
    from nabla.api.external_probe_cache_redis import resolve_redis_client  # noqa: PLC0415
    return resolve_redis_client()


def register_routes(app: FastAPI) -> None:
    @app.post(INGEST_PATH, include_in_schema=False)
    async def receive(request: Request) -> JSONResponse:
        if not publication_enabled() or not _secret() or not fastapi_cloud_runtime_detected(request.url.hostname):
            return JSONResponse({"state": "disabled"}, status_code=404, headers=_NOCACHE)
        signatures = request.headers.getlist(SIGNATURE_HEADER)
        if len(signatures) != 1 or not _SIGNATURE.fullmatch(signatures[0]):
            return JSONResponse({"state": "signature_required"}, status_code=401, headers=_NOCACHE)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return JSONResponse({"state": "json_required"}, status_code=415, headers=_NOCACHE)
        body = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        return JSONResponse({"state": "too_large"}, status_code=413, headers=_NOCACHE)
                    body.extend(chunk)
        except TimeoutError:
            return JSONResponse({"state": "body_timeout"}, status_code=408, headers=_NOCACHE)
        raw = bytes(body)
        if not hmac.compare_digest(sign(raw, _secret()), signatures[0]):
            return JSONResponse({"state": "invalid_signature"}, status_code=401, headers=_NOCACHE)
        try:
            batch = validate_batch(json.loads(raw))
        except (ValueError, UnicodeError, RecursionError):
            batch = None
        if batch is None:
            return JSONResponse({"state": "invalid_batch"}, status_code=422, headers=_NOCACHE)
        redis = _redis()
        if redis is None:
            return JSONResponse({"state": "storage_unavailable"}, status_code=503, headers=_NOCACHE)
        try:
            accepted = await asyncio.wait_for(
                redis.eval(_CAS, 1, _CACHE_KEY, json.dumps(batch, separators=(",", ":")), int(time.time())),
                timeout=0.8,
            )
        except Exception:
            return JSONResponse({"state": "storage_unavailable"}, status_code=503, headers=_NOCACHE)
        return JSONResponse(
            {"state": "accepted" if accepted == 1 else "stale"},
            status_code=202 if accepted == 1 else 409,
            headers=_NOCACHE,
        )

    @app.get(PUBLIC_PATH, include_in_schema=False)
    async def published() -> JSONResponse:
        if not publication_enabled() or not fastapi_cloud_runtime_detected():
            return JSONResponse({"state": "disabled"}, status_code=404, headers=_NOCACHE)
        redis = _redis()
        if redis is None:
            return JSONResponse({"state": "unavailable"}, status_code=503, headers=_NOCACHE)
        try:
            data = await asyncio.wait_for(redis.get(_CACHE_KEY), timeout=0.2)
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if not isinstance(data, str) or len(data) > 40000:
                raise ValueError("missing RSS publication")
            projected = _safe_record(json.loads(data), now=int(time.time()))
        except Exception:
            projected = None
        if projected is None:
            return JSONResponse({"state": "unavailable"}, status_code=503, headers=_NOCACHE)
        return JSONResponse(
            projected,
            headers={"Cache-Control": "public, max-age=0, s-maxage=120", "X-Content-Type-Options": "nosniff"},
        )


async def publish(rows: list[dict[str, Any]], *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """TrueNAS-only, explicitly approved outbound publication; no site credentials."""
    if not homelab_runtime_detected() or not _secret():
        return "disabled"
    target = str(getattr(get_settings(), "truenas_federation_cloud_url", "") or "").rstrip("/")
    if target != "https://fastapi-sample.fastapicloud.dev":
        return "unapproved_target"
    batch = build_batch(rows)
    raw = json.dumps(batch, separators=(",", ":"), sort_keys=True).encode()
    if len(raw) > MAX_BODY_BYTES:
        return "over_budget"
    try:
        async with httpx.AsyncClient(
            timeout=3.0, follow_redirects=False, trust_env=False, transport=transport
        ) as client:
            response = await client.post(
                target + INGEST_PATH,
                content=raw,
                headers={"Content-Type": "application/json", SIGNATURE_HEADER: sign(raw, _secret())},
            )
        return "sent" if response.status_code == 202 else f"http_{response.status_code}"
    except httpx.HTTPError:
        return "network_unavailable"
