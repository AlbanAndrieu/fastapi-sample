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
from nabla.api.runtime_environment import runtime_mode
from nabla.utils.logger import logger

_RUNTIME_KEY_PREFIX = "fastapi-sample:runtime"
_HEARTBEAT_INTERVAL_SEC = 30.0
_ACTIVE_WINDOW_SEC = 95.0
_RECENT_EGRESS_WINDOW_SEC = 86_400.0
_INSTANCE_REGISTRY_TTL_SEC = 600
_EGRESS_REGISTRY_TTL_SEC = 172_800
_REDIS_TELEMETRY_TIMEOUT_SEC = 1.5


def runtime_registry_keys(mode: str | None = None) -> tuple[str, str, str]:
    """Return Redis keys isolated by runtime scope to avoid local/cloud mixing."""
    scope = mode or runtime_mode()
    prefix = f"{_RUNTIME_KEY_PREFIX}:{scope}"
    return (
        f"{prefix}:instances:last-seen",
        f"{prefix}:instances:details",
        f"{prefix}:egress:last-seen",
    )


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


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


async def redis_usage_snapshot(redis_client: Redis | None) -> dict[str, Any]:
    """Return bounded, credential-free Redis capacity/usage telemetry."""
    if redis_client is None:
        return {
            "available": False,
            "telemetry_available": False,
            "reason": "redis client not configured",
        }

    try:
        async with asyncio.timeout(_REDIS_TELEMETRY_TIMEOUT_SEC):
            memory, clients, stats, key_count = await asyncio.gather(
                redis_client.info("memory"),
                redis_client.info("clients"),
                redis_client.info("stats"),
                redis_client.dbsize(),
            )
    except TimeoutError:
        return {
            "available": True,
            "telemetry_available": False,
            "reason": "redis telemetry deadline exceeded",
            "error_kind": "deadline",
        }
    except Exception as exc:
        return {
            "available": True,
            "telemetry_available": False,
            "reason": "redis telemetry unavailable",
            "exception_type": type(exc).__name__,
        }

    used_memory = _int_value(memory.get("used_memory"))
    maxmemory = _int_value(memory.get("maxmemory"))
    utilization = None
    if used_memory is not None and maxmemory is not None and maxmemory > 0:
        utilization = round((used_memory / maxmemory) * 100, 2)

    return {
        "available": True,
        "telemetry_available": True,
        "used_memory_bytes": used_memory,
        "used_memory_human": memory.get("used_memory_human"),
        "used_memory_rss_bytes": _int_value(memory.get("used_memory_rss")),
        "used_memory_rss_human": memory.get("used_memory_rss_human"),
        "used_memory_peak_bytes": _int_value(memory.get("used_memory_peak")),
        "used_memory_peak_human": memory.get("used_memory_peak_human"),
        "maxmemory_bytes": maxmemory,
        "maxmemory_human": memory.get("maxmemory_human"),
        "maxmemory_policy": memory.get("maxmemory_policy"),
        "memory_utilization_percent": utilization,
        "mem_fragmentation_ratio": _float_value(memory.get("mem_fragmentation_ratio")),
        "connected_clients": _int_value(clients.get("connected_clients")),
        "blocked_clients": _int_value(clients.get("blocked_clients")),
        "keys": _int_value(key_count),
        "instantaneous_ops_per_sec": _int_value(stats.get("instantaneous_ops_per_sec")),
        "keyspace_hits": _int_value(stats.get("keyspace_hits")),
        "keyspace_misses": _int_value(stats.get("keyspace_misses")),
        "evicted_keys": _int_value(stats.get("evicted_keys")),
        "expired_keys": _int_value(stats.get("expired_keys")),
    }


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

    instance_zset, instance_hash, egress_zset = runtime_registry_keys()
    stale_before = now - _ACTIVE_WINDOW_SEC
    try:
        stale_ids = await redis_client.zrangebyscore(instance_zset, min="-inf", max=stale_before)
        pipeline = redis_client.pipeline(transaction=False)
        pipeline.zadd(instance_zset, {instance_id: now})
        pipeline.hset(instance_hash, instance_id, json.dumps(details, separators=(",", ":")))
        if stale_ids:
            pipeline.zrem(instance_zset, *stale_ids)
            pipeline.hdel(instance_hash, *stale_ids)
        egress_ip = details.get("egress_ip")
        if isinstance(egress_ip, str) and egress_ip:
            pipeline.zadd(egress_zset, {egress_ip: now})
        pipeline.zremrangebyscore(egress_zset, min="-inf", max=now - _RECENT_EGRESS_WINDOW_SEC)
        pipeline.expire(instance_zset, _INSTANCE_REGISTRY_TTL_SEC)
        pipeline.expire(instance_hash, _INSTANCE_REGISTRY_TTL_SEC)
        pipeline.expire(egress_zset, _EGRESS_REGISTRY_TTL_SEC)
        await pipeline.execute()
    except Exception as exc:  # Redis telemetry must never affect application health.
        logger.warning(
            "runtime_topology_heartbeat_failed",
            exception_type=type(exc).__name__,
        )
    return details


async def _shared_runtime_snapshot(redis_client: Redis, current: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    instance_zset, instance_hash, egress_zset = runtime_registry_keys()
    active_after = now - _ACTIVE_WINDOW_SEC
    active_ids = await redis_client.zrangebyscore(instance_zset, min=active_after, max="+inf")
    raw_details = await redis_client.hmget(instance_hash, active_ids) if active_ids else []
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
        egress_zset,
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
    mode = runtime_mode()
    current = await record_runtime_heartbeat(redis_client)
    redis_usage = await redis_usage_snapshot(redis_client)
    shared: dict[str, Any]
    if redis_client is None:
        shared = {
            "observed_instance_count": 1,
            "instances": [current],
            "active_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
            "recent_egress_ips": [current["egress_ip"]] if current.get("egress_ip") else [],
            "aggregation": "local_only",
            "degraded": mode == "fastapi_cloud",
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

    is_fastapi_cloud = mode == "fastapi_cloud"
    return {
        "provider": "FastAPI Cloud" if is_fastapi_cloud else "Local workstation",
        "runtime_mode": mode,
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
        "redis": redis_usage,
        **shared,
    }


async def runtime_topology_heartbeat(redis_client: Redis) -> None:
    """Keep this replica present in the shared runtime registry."""
    while True:
        await record_runtime_heartbeat(redis_client)
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SEC)
