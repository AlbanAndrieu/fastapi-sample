"""Opt-in Redis history of minimal OWNER service observations.

Only direct-probe states are saved. No URLs, credentials, IPs, headers,
descriptions or raw health-board responses leave process memory.
An old observation is never proof of current service health.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import os
import re
import time
from typing import Any

from nabla.utils.logger import logger

_ENABLED = "HOMELAB_OWNER_HISTORY_REDIS_ENABLED"
_NAMESPACE = "HOMELAB_OWNER_HISTORY_NAMESPACE"
_PREFIX = "health:v2:owner:last-known:"
_TTL_SECONDS = 7 * 24 * 60 * 60
_IO_TIMEOUT_SECONDS = 0.5
_MAX_RECORDS = 512
_MAX_NEW_RECORDS = 256
_MAX_RECORD_BYTES = 350
_VALID_NAMESPACE = re.compile(r"[a-z0-9][a-z0-9_-]{2,47}\Z")
_VALID_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_VALID_STATES = frozenset({"ok", "warn", "fail", "expected"})
_SCOPES = ("public", "internal")


def _redis_key() -> str | None:
    if os.getenv(_ENABLED, "").lower() != "true":
        return None
    namespace = os.getenv(_NAMESPACE, "")
    if not _VALID_NAMESPACE.fullmatch(namespace):
        return None
    identity = "|".join(
        (namespace, os.getenv("FASTAPI_RUNTIME_MODE", ""), os.getenv("APP_DOMAIN", "")),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"{_PREFIX}{namespace}:{digest}"


def resolve_redis_client() -> Any | None:
    """Resolve lazily: no Redis connection or probe during module import."""
    try:
        from nabla.api.external_probe_cache_redis import resolve_redis_client as resolve  # noqa: PLC0415
    except (ImportError, RuntimeError):
        return None
    return resolve()


def _timestamp(value: object, now: float) -> float | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    observed_time = observed.timestamp()
    if not now - _TTL_SECONDS <= observed_time <= now + 60:
        return None
    return observed_time


def _record(value: object, now: float) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    service_id = value.get("id")
    state = value.get("state")
    scope = value.get("scope")
    observed_at = value.get("observedAt")
    if (
        not isinstance(service_id, str)
        or not _VALID_ID.fullmatch(service_id)
        or not isinstance(state, str)
        or state not in _VALID_STATES
        or not isinstance(scope, str)
        or scope not in _SCOPES
        or _timestamp(observed_at, now) is None
    ):
        return None
    return {
        "id": service_id,
        "state": state,
        "scope": scope,
        "observedAt": observed_at,
    }


def _from_snapshot(snapshot: dict[str, Any], now: float) -> dict[str, dict[str, str]]:
    homelab = snapshot.get("homelab")
    if not isinstance(homelab, dict):
        return {}
    collected: dict[str, dict[str, str]] = {}
    for scope, name in (("public", "services"), ("internal", "internal_services")):
        rows = homelab.get(name)
        if not isinstance(rows, list):
            continue
        for row in rows[:_MAX_NEW_RECORDS]:
            if (
                not isinstance(row, dict)
                or row.get("probe_source") != "origin"
                or row.get("probe_stale") is True
            ):
                continue
            record = _record(
                {
                    "id": row.get("id"),
                    "scope": scope,
                    "state": row.get("state"),
                    "observedAt": row.get("probe_observed_at"),
                },
                now,
            )
            if record is not None:
                collected[f"{scope}:{record['id']}"] = record
    return collected


async def write_owner_last_known(snapshot: dict[str, Any]) -> bool:
    """Atomically persist only new direct probes with bounded expiration."""
    key = _redis_key()
    if key is None:
        return False
    rows = _from_snapshot(snapshot, time.time())
    if not rows:
        return False
    client = resolve_redis_client()
    if client is None:
        return False
    try:
        mapping = {
            name: json.dumps(record, separators=(",", ":"))
            for name, record in rows.items()
        }
        # Transactional hash updates preserve other rotating probes and
        # ensure expiration cannot be omitted after writing sensitive state.
        pipeline = client.pipeline(transaction=True)
        pipeline.hset(key, mapping=mapping)
        pipeline.expire(key, _TTL_SECONDS)
        await asyncio.wait_for(pipeline.execute(), timeout=_IO_TIMEOUT_SECONDS)
        return True
    except Exception as exc:
        logger.warning(
            "owner_last_known_write_failed",
            exception_type=type(exc).__name__,
        )
        return False


async def read_owner_last_known() -> dict[str, Any]:
    """Return a minimal, dated payload after route-level OWNER authorization."""
    key = _redis_key()
    if key is None:
        return {"state": "disabled", "observations": []}
    client = resolve_redis_client()
    if client is None:
        return {"state": "unavailable", "observations": []}
    try:
        entries = await asyncio.wait_for(
            client.hgetall(key),
            timeout=_IO_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "owner_last_known_read_failed",
            exception_type=type(exc).__name__,
        )
        return {"state": "unavailable", "observations": []}
    if not isinstance(entries, dict) or len(entries) > _MAX_RECORDS:
        return {"state": "unavailable", "observations": []}
    now = time.time()
    rows: list[dict[str, Any]] = []
    for raw_key, raw_value in entries.items():
        if isinstance(raw_key, bytes):
            raw_key = raw_key.decode("utf-8", errors="replace")
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8", errors="replace")
        if not isinstance(raw_value, str) or len(raw_value) > _MAX_RECORD_BYTES:
            continue
        try:
            record = _record(json.loads(raw_value), now)
        except (TypeError, ValueError):
            continue
        if record is None or raw_key != f"{record['scope']}:{record['id']}":
            continue
        observed = _timestamp(record["observedAt"], now)
        if observed is not None:
            rows.append({
                **record,
                "ageSeconds": round(max(0.0, now - observed), 1),
            })
    rows.sort(key=lambda row: (row["ageSeconds"], row["id"], row["scope"]))
    return {"state": "historical", "current": False, "observations": rows}
