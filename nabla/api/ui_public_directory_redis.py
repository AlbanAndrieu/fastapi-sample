"""Optional Redis L2 for public service DIRECTORY ONLY, not health state.

Only approved public names, kinds and revision are persisted. Each read
reconstructs UNKNOWN statuses. Redis is never an authorization boundary.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,47}$")
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()+&-]{0,127}$")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_REVISION = re.compile(r"^sha256:[a-f0-9]{64}$")
_KINDS = frozenset({"API", "Component", "Resource"})
_TTL_SECONDS = 300
_TIMEOUT_SECONDS = 0.15
_MAX_BYTES = 200_000
_PREFIX = "nabla:home:public-directory:v1:"


def _cache_key() -> str | None:
    if os.getenv("NABLA_PUBLIC_DIRECTORY_REDIS_ENABLED", "").strip().lower() != "true":
        return None
    namespace = os.getenv("NABLA_PUBLIC_DIRECTORY_REDIS_NAMESPACE", "").strip().lower()
    if not _NAMESPACE.fullmatch(namespace):
        return None
    return _PREFIX + namespace


def resolve_redis_client() -> Any | None:
    if _cache_key() is None:
        return None
    try:
        from nabla.api.external_probe_cache_redis import resolve_redis_client as resolver
        return resolver()
    except (ImportError, RuntimeError):
        return None


def _safe_directory(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    revision = value.get("catalogRevision")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        return None
    rows = value.get("services")
    if not isinstance(rows, list) or not 0 < len(rows) <= 1000:
        return None
    names: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        kind = item.get("kind")
        if not isinstance(name, str) or not _LABEL.fullmatch(name) or _IP.search(name):
            return None
        if kind not in _KINDS:
            return None
        names.append({"name": name, "kind": kind, "state": "unknown"})
    return {
        "schemaVersion": 2,
        "model": "public-service-overview",
        "catalogRevision": revision,
        "catalogSource": "bootstrap-snapshot",
        "boardState": "pending",
        "services": names,
    }


async def read_public_directory_redis() -> Any | None:
    """Return a strict public model; never restore OK/WARN/FAIL from Redis."""
    key = _cache_key()
    client = resolve_redis_client()
    if key is None or client is None:
        return None
    try:
        raw = await asyncio.wait_for(client.get(key), timeout=_TIMEOUT_SECONDS)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="strict")
        if not isinstance(raw, str) or len(raw) > _MAX_BYTES:
            return None
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or envelope.get("version") != 1:
            return None
        stored_at = envelope.get("storedAt")
        if not isinstance(stored_at, (int, float)) or isinstance(stored_at, bool):
            return None
        age = time.time() - stored_at
        if age < -30 or age > _TTL_SECONDS:
            return None
        safe = _safe_directory(envelope.get("directory"))
        if safe is None:
            return None
        from nabla.api.ui_public_services import PublicUiServices  # noqa: PLC0415
        return PublicUiServices.model_validate(safe)
    except Exception:
        return None


async def write_public_directory_redis(payload: Any) -> bool:
    """Store only names/kinds from canonical public catalog, never observations."""
    key = _cache_key()
    client = resolve_redis_client()
    if key is None or client is None or getattr(payload, "catalogSource", None) != "backstage-v2":
        return False
    try:
        safe = _safe_directory(payload.model_dump())
        if safe is None:
            return False
        value = json.dumps(
            {"version": 1, "storedAt": time.time(), "directory": safe},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        if len(value) > _MAX_BYTES:
            return False
        await asyncio.wait_for(
            client.set(key, value, ex=_TTL_SECONDS),
            timeout=_TIMEOUT_SECONDS,
        )
        return True
    except Exception:
        return False
