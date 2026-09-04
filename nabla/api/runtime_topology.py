"""Best-effort cross-replica runtime and public-egress observation.

FastAPI Cloud exposes replica counts in its control-plane Metrics UI, but the
application runtime does not currently receive a documented control-plane replica
count.  This module therefore reports *observed active runtimes* using short-lived
Redis heartbeats.  It never presents that count as the authoritative platform
replica count.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
import socket
import time
from typing import Any

from redis.asyncio import Redis

from nabla.api.public_egress_observer import observe_public_egress_ip
from nabla.utils.logger import logger

_INSTANCE_ZSET = "fastapi-sample:runtime:instances:last-seen"
_INSTANCE_HASH = "fastapi-sample:runtime:instances:details"
_EGRESS_ZSET = "fastapi-sample:runtime:egress:last-seen"
_HEARTBEAT_INTERVAL_SEC = 30.0
_ACTIVE_WINDOW_SEC = 95.0
_RECENT_EGRESS_WINDOW_SEC = 86_400.0


def _utc_timestamp(epoch: float | None = None) -> str:
    value = time.time() if epoch is None else epoch
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def _instance_seed() -> str:
    """Return a stable per-container seed without publishing internal hostnames."""
    return os.getenv("HOSTNAME", "").strip() or socket.gethostname()


def runtime_instance_id() -> str:
    """Return an opaque stable identifier for this application runtime container."""
    digest = hashlib.sha256(_instance_seed().encode("utf-8")).hexdigest()[:12]
    return f"runtime-{digest}"


def _decode_json(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


async def record_runtime_heartbeat(redis_client: Redis | None) -> dict[str, Any]:
    """Record this runtime in the shared registry and return its sanitized details."""
    egress = await observe_public_egress_ip()
    now = time.time()
    instance_id = runtime_instance_id()
    details: dict[str, Any] = {
        "id": instance_id,
        "last_seen_at": _utc_timestamp(now),
        "egress_ip": egress.get("ip") if egress.get("observed") is True else None,
        "egress_observed": egress.get("observed") is True,
        "egress_cached": bool(egress.get("cached")),
    }
    if redis_client is None:
        return details

    stale_before = now - _ACTIVE_WINDOW_SEC
    try:
        stale_ids = await redis_client.zrangebyscore(_INSTANCE_ZSET, min="-inf", max=stale_before)
        pipeline = redis_client.pipeline(transaction=False)
        pipeline.zadd(_INSTANCE_ZSET, {instance_id: now})
        pipeline.hset(_INSTANCE_HASH, instance_id, json.dumps(details, separators=(",", ":")))
        if stale_ids:
            pipeline.zrem(_INSTANCE_ZSET, *stale_ids)
            pipeline.hdel(_INSTANCE_HASH, *stale_ids)
        egress_ip = details.get("egress_ip")
        if isinstance(egress_ip, str) and egress_ip:
            pipeline.zadd(_EGRESS_ZSET, {egress_ip: now})
        pipeline.zremrangebyscore(_EGRESS_ZSET, min="-inf", max=now - _RECENT_EGRESS_WINDOW_SEC)
        await pipeline.execute()
    except Exception as exc:  # Redis telemetry must never affect application health.
        logger.warning(
            "runtime_topology_heartbeat_failed",
            exception_type=type(exc).__name__,
        )
    return details


async def _shared_runtime_snapshot(redis_client: Redis, current: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    active_after = now - _ACTIVE_WINDOW_SEC
    active_ids = await redis_client.zrangebyscore(_INSTANCE_ZSET, min=active_after, max="+inf")
    raw_details = await redis_client.hmget(_INSTANCE_HASH, active_ids) if active_ids else []
    instances = [value for value in (_decode_json(raw) for raw in raw_details) if value is not None]
    if current["id"] not in {item.get("id") for item in instances}:
        instances.append(current)

    active_egress = sorted(
        {
            str(item["egress_ip"])
            for item in instances
            if isinstance(item.get("egress_ip"), str) and item.get("egress_ip")
        }
    )
    recent_egress = await redis_client.zrangebyscore(
        _EGRESS_ZSET,
        min=now - _RECENT_EGRESS_WINDOW_SEC,
        max="+inf",
    )
    return {
        "observed_instance_count": len(instances),
        "instances": sorted(instances, key=lambda item: str(item.get("id") or "")),
        "active_egress_ips": active_egress,
        "recent_egress_ips": sorted({str(value) for value in recent_egress}),
        "aggregation": "redis_heartbeat",
        "degraded": False,
    }


async def build_runtime_topology_snapshot(redis_client: Redis | None) -> dict[str, Any]:
    """Return active runtime/egress evidence with explicit count semantics."""
    current = await record_runtime_heartbeat(redis_client)
    shared: dict[str, Any]
    if redis_client is None:
        shared = {
            "observed_instance_count": 1,
            "instances": [current],
            "active_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
            "recent_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
            "aggregation": "local_only",
            "degraded": True,
        }
    else:
        try:
            shared = await _shared_runtime_snapshot(redis_client, current)
        except Exception as exc:  # Best-effort diagnostic only.
            logger.warning(
                "runtime_topology_snapshot_failed",
                exception_type=type(exc).__name__,
            )
            shared = {
                "observed_instance_count": 1,
                "instances": [current],
                "active_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
                "recent_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
                "aggregation": "local_fallback",
                "degraded": True,
            }

    is_fastapi_cloud = bool(os.getenv("FASTAPI_CLOUD", "").strip())
    return {
        "provider": "FastAPI Cloud" if is_fastapi_cloud else "Local workstation",
        "runtime_mode": "fastapi_cloud" if is_fastapi_cloud else "local",
        "observed_at": _utc_timestamp(),
        "platform_replica_count": None,
        "platform_replica_count_available": False,
        "count_semantics": (
            "Observed active application runtimes from shared heartbeats; "
            "this is not the FastAPI Cloud control-plane replica count."
            if is_fastapi_cloud
            else "Observed application runtimes for the local workstation; "
            "shared Redis heartbeats may include sibling local processes."
        ),
        "heartbeat_interval_seconds": int(_HEARTBEAT_INTERVAL_SEC),
        "active_window_seconds": int(_ACTIVE_WINDOW_SEC),
        "recent_egress_window_seconds": int(_RECENT_EGRESS_WINDOW_SEC),
        **shared,
    }


async def runtime_topology_heartbeat(redis_client: Redis) -> None:
    """Keep this replica present in the shared runtime registry."""
    while True:
        await record_runtime_heartbeat(redis_client)
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SEC)
