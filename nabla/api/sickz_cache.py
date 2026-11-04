"""Process-local single-flight cache for the public ``/sickz`` snapshot.

Each origin ``/sickz`` build probes every declared exposure group (about 70
targets) and enriches the result with Cloudflare policy evidence, which takes
roughly 8-11 seconds. Without a cache, every anonymous request repeated that
fan-out towards the homelab WAN and Cloudflare. The cache bounds the origin
fan-out to at most one build per TTL per worker, whatever the request rate,
without relying on client-IP rate limiting behind the PaaS proxy.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
import time
from typing import Any

from fastapi import Request

SICKZ_CACHE_TTL_SECONDS = 60.0

_lock = asyncio.Lock()
_snapshot: dict[str, Any] | None = None
_snapshot_key: str | None = None
_cached_at = 0.0


def _now() -> float:
    return time.monotonic()


def _cache_key(request: Request) -> str:
    """Policy annotations depend on the runtime scope derived from the hostname."""
    return (request.url.hostname or "").lower()


async def cached_sickz_snapshot(
    request: Request,
    builder: Callable[[Request], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Return a fresh-enough snapshot, building it at most once concurrently."""
    global _snapshot, _snapshot_key, _cached_at
    key = _cache_key(request)
    async with _lock:
        age = _now() - _cached_at
        if _snapshot is not None and _snapshot_key == key and age < SICKZ_CACHE_TTL_SECONDS:
            return {
                **deepcopy(_snapshot),
                "probe_cache": {"source": "cache", "age_seconds": round(age, 3), "ttl_seconds": SICKZ_CACHE_TTL_SECONDS},
            }
        snapshot = await builder(request)
        _snapshot, _snapshot_key, _cached_at = deepcopy(snapshot), key, _now()
    return {
        **snapshot,
        "probe_cache": {"source": "origin", "age_seconds": 0.0, "ttl_seconds": SICKZ_CACHE_TTL_SECONDS},
    }


async def reset_sickz_cache() -> None:
    """Drop the cached snapshot so the next request rebuilds it from origin."""
    global _snapshot, _snapshot_key, _cached_at
    async with _lock:
        _snapshot, _snapshot_key, _cached_at = None, None, 0.0
