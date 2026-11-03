"""Opt-in, bounded Redis sharing of sanitized PUBLIC probe evidence.

No LAN target, credential, header or full URL is written to Redis.
Redis failures fall back to process-local evidence and never block startup.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from typing import Any

from nabla.api.external_probe_cache_redis import resolve_redis_client
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_evidence import MAX_PROBE_EVIDENCE_RETENTION_SEC
from nabla.utils.environment import env_bool
from nabla.utils.logger import logger

_ENABLED_ENV = "HOMELAB_PUBLIC_PROBE_EVIDENCE_REDIS_ENABLED"
_NAMESPACE_ENV = "HOMELAB_PROBE_EVIDENCE_NAMESPACE"
_KEY_PREFIX = "health:v2:public-evidence:"
_SCHEMA = 1
_IO_BUDGET_SECONDS = 0.5

# Retain scalar, non-secret diagnostics. Origin URLs and host data come only
# from the locally approved catalog when an entry is rehydrated.
_FIELDS = frozenset({
    "reachable", "http_status", "state", "tls_trusted", "latency_ms",
    "anonymous_http_status", "origin_reached", "dns_state", "error_kind",
    "public_probe_auth_mode", "public_probe_verification",
    "cloudflare_access_signal", "cloudflare_default_deny",
    "cloudflare_service_token_rejected",
})


def _key(service_id: str) -> str | None:
    namespace = os.getenv(_NAMESPACE_ENV, "default")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", namespace):
        return None
    digest = hashlib.sha256(service_id.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}{namespace}:{digest}"


def _client() -> Any | None:
    if not env_bool(_ENABLED_ENV):
        return None
    return resolve_redis_client()


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip non-primitive fields and constrain status/health vocabulary."""
    safe = {}
    for field in _FIELDS:
        value = row.get(field)
        if value is None or isinstance(value, (bool, int, float)):
            safe[field] = value
        elif isinstance(value, str) and len(value) <= 128:
            safe[field] = value
    return safe


async def read_public_probe_evidence(
    candidates: list[HomelabService],
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch prior public observations for this catalog, if explicitly enabled."""
    client = _client()
    if client is None:
        return [], False
    keys = [_key(service.service_id) for service in candidates]
    if any(key is None for key in keys):
        return [], False
    if not keys:
        return [], True
    try:
        raw_values = await asyncio.wait_for(client.mget(keys), timeout=_IO_BUDGET_SECONDS)
    except Exception as exc:
        logger.warning("public_probe_shared_read_failed", exception_type=type(exc).__name__)
        return [], False
    entries = []
    for service, raw in zip(candidates, raw_values, strict=False):
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if not isinstance(raw, str):
            continue
        try:
            envelope = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if (
            isinstance(envelope, dict)
            and envelope.get("schema") == _SCHEMA
            and envelope.get("service_id") == service.service_id
            and isinstance(envelope.get("row"), dict)
        ):
            envelope["row"] = _safe_row(envelope["row"])
            entries.append(envelope)
    return entries, True


async def write_public_probe_evidence(
    rows: list[dict[str, Any]], checked_at: str,
) -> bool:
    """Persist only new public-origin observations with a bounded Redis TTL."""
    client = _client()
    if client is None:
        return False
    writes = []
    for row in rows:
        service_id = row.get("id")
        if not isinstance(service_id, str) or row.get("probe_source") != "origin":
            continue
        key = _key(service_id)
        if key is None:
            return False
        envelope = {
            "schema": _SCHEMA,
            "service_id": service_id,
            "observed_at": checked_at,
            "row": _safe_row(row),
        }
        writes.append(
            client.set(
                key,
                json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                ex=int(MAX_PROBE_EVIDENCE_RETENTION_SEC),
            )
        )
    try:
        if writes:
            await asyncio.wait_for(asyncio.gather(*writes), timeout=_IO_BUDGET_SECONDS)
        return True
    except Exception as exc:
        logger.warning("public_probe_shared_write_failed", exception_type=type(exc).__name__)
        return False
