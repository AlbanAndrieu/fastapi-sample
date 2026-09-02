# ruff: noqa: PLC0415, PLW0603 -- probes stay lazy and cache state is process-local.
"""Single-flight, stale-while-revalidate snapshot for the public health board."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import logging
import os
import time
from typing import Any

from fastapi import Request

from nabla.api.health_contracts import apply_diagnostic_status

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 30.0
_MIN_TTL_SECONDS = 10.0
_MAX_TTL_SECONDS = 300.0
_cache_lock = asyncio.Lock()
_cached_snapshot: dict[str, Any] | None = None
_cached_at = 0.0
_refresh_task: asyncio.Task[None] | None = None
_last_refresh_error: str | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _ttl_seconds() -> float:
    raw = os.getenv("HEALTH_BOARD_CACHE_TTL_SECONDS", "").strip()
    try:
        configured = float(raw) if raw else _DEFAULT_TTL_SECONDS
    except ValueError:
        configured = _DEFAULT_TTL_SECONDS
    return max(_MIN_TTL_SECONDS, min(configured, _MAX_TTL_SECONDS))


def _short_error(exc: BaseException) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:240]


async def build_extended_healthz(request: Request) -> dict[str, Any]:
    """Build the backward-compatible deep diagnostic payload."""
    from nabla.api.db.database import engine
    from nabla.api.demo.socket.redis import redis
    from nabla.api.health_checks import build_healthz_payload
    from nabla.api.observability_health import enrich_optional_observability_checks
    from nabla.api.platform_health import enrich_optional_platform_checks

    payload = await build_healthz_payload(request, redis_client=redis, engine=engine)
    payload = await enrich_optional_platform_checks(payload)
    payload = await enrich_optional_observability_checks(payload)
    return apply_diagnostic_status(payload)


async def build_homelab_snapshot(
    shared_checks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from nabla.api.component_health import (
        build_component_checks,
        component_status,
        truenas_component,
    )
    from nabla.api.db.database import engine
    from nabla.api.demo.socket.redis import redis
    from nabla.api.homelab_health import build_homelab_health_payload
    from nabla.api.homelab_health_evidence import reconcile_homelab_health_payload
    from nabla.api.provider_credentials import infrastructure_provider_credentials

    homelab_task = asyncio.create_task(build_homelab_health_payload())
    if shared_checks is None:
        components = await build_component_checks(
            redis_client=redis,
            engine=engine,
            homelab_snapshot=homelab_task,
        )
    else:
        homelab = await homelab_task
        components = {
            key: shared_checks.get(key, {"reachable": None, "skipped": True})
            for key in ("postgres", "redis", "supabase", "cloudflare", "pfsense")
        }
        components["truenas"] = truenas_component(homelab)
    payload = await reconcile_homelab_health_payload(await homelab_task)
    payload["components_status"] = component_status(components)
    payload["components"] = components
    payload["provider_credentials"] = infrastructure_provider_credentials()
    return payload


async def build_sickz_snapshot(request: Request) -> dict[str, Any]:
    from nabla.api.sickz_checks import build_sickz_payload
    from nabla.api.sickz_policy import enrich_sickz_policy
    from nabla.api.sickz_port_annotations import enrich_pfsense_port_annotations

    payload = await enrich_sickz_policy(await build_sickz_payload(request))
    return enrich_pfsense_port_annotations(payload)


async def build_runtime_snapshot() -> dict[str, Any]:
    """Return the shared runtime/egress view used by the public API page."""
    from nabla.api.demo.socket.redis import redis
    from nabla.api.runtime_topology import build_runtime_topology_snapshot

    return await build_runtime_topology_snapshot(redis)


async def build_health_board_snapshot(request: Request) -> dict[str, Any]:
    """Collect expensive views sequentially so one UI load cannot amplify fan-out."""
    healthz = await build_extended_healthz(request)
    runtime = await build_runtime_snapshot()
    homelab = await build_homelab_snapshot(healthz.get("checks"))
    sickz = await build_sickz_snapshot(request)
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runtime": runtime,
        "healthz": healthz,
        "homelab": homelab,
        "sickz": sickz,
    }


async def _refresh(request: Request) -> None:
    global _cached_at, _cached_snapshot, _last_refresh_error
    started = time.monotonic()
    try:
        snapshot = await build_health_board_snapshot(request)
    except Exception as exc:
        _last_refresh_error = _short_error(exc)
        logger.warning(
            "health board snapshot refresh failed duration_seconds=%.3f error=%s",
            time.monotonic() - started,
            _last_refresh_error,
        )
        return

    async with _cache_lock:
        _cached_snapshot = snapshot
        _cached_at = time.monotonic()
        _last_refresh_error = None
    logger.info(
        "health board snapshot refreshed duration_seconds=%.3f",
        time.monotonic() - started,
    )


def _task_is_running() -> bool:
    return _refresh_task is not None and not _refresh_task.done()


async def get_health_board_snapshot(
    request: Request,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return a fresh/stale snapshot immediately and refresh it in the background."""
    global _refresh_task

    async with _cache_lock:
        age = time.monotonic() - _cached_at if _cached_snapshot is not None else None
        fresh = age is not None and age < _ttl_seconds()
        if (force_refresh or not fresh) and not _task_is_running():
            _refresh_task = asyncio.create_task(
                _refresh(request),
                name="health-board-refresh",
            )
        snapshot = deepcopy(_cached_snapshot)
        refreshing = _task_is_running()
        error = _last_refresh_error

    if snapshot is None:
        return {
            "schema_version": 1,
            "state": "pending",
            "refreshing": refreshing,
            "retry_after_seconds": 2,
            "generated_at": None,
            "error": error,
            "runtime": None,
            "healthz": None,
            "homelab": None,
            "sickz": None,
        }
    return {
        **snapshot,
        "state": "fresh" if fresh and not force_refresh else "stale",
        "refreshing": refreshing,
        "age_seconds": round(age or 0.0, 3),
        "error": error,
    }


async def reset_health_board_cache() -> None:
    """Reset module state for deterministic tests."""
    global _cached_at, _cached_snapshot, _last_refresh_error, _refresh_task
    async with _cache_lock:
        task = _refresh_task
        _refresh_task = None
        _cached_snapshot = None
        _cached_at = 0.0
        _last_refresh_error = None
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
