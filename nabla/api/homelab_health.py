# ruff: noqa: PLW0603 -- the module owns one lock-protected snapshot cache.

"""Cached health snapshots for external and optional internal homelab probes."""

from __future__ import annotations

import asyncio
from functools import partial
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from nabla.api import homelab_probe_batch, homelab_probe_runner, truenas_probe_health
from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_truenas_probe import probe_truenas
from nabla.api.homelab_health_cache import copy_homelab_health_payload
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_evidence import (
    evidence_summary,
    merge_probe_evidence,
)
from nabla.api.homelab_probe_policy import (
    HEALTH_CACHE_TTL_SEC as _HEALTH_CACHE_TTL_SEC,
    INTERNAL_PROBE_TIMEOUT_SEC as _INTERNAL_PROBE_TIMEOUT_SEC,
    MAX_INTERNAL_PROBES_PER_REFRESH as _MAX_INTERNAL_PROBES_PER_REFRESH,
    MAX_PROBE_CONCURRENCY as _MAX_PROBE_CONCURRENCY,
    MAX_PUBLIC_PROBES_PER_REFRESH as _MAX_PUBLIC_PROBES_PER_REFRESH,
    PUBLIC_PROBE_TIMEOUT_SEC as _PUBLIC_PROBE_TIMEOUT_SEC,
    SERVICE_FANOUT_BUDGET_SEC as _SERVICE_FANOUT_BUDGET_SEC,
    priority_source as _priority_source,
    rotated_priority_ids as _rotated_priority_ids,
    select_probe_subset as _select_probe_subset,
)
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence
from nabla.utils.environment import env_bool

_PROBE_TIMEOUT_SEC = 5.0
_INTERNAL_PROBE_ENV = "HOMELAB_INTERNAL_PROBES_ENABLED"
_cache_lock = asyncio.Lock()
_cached_at = 0.0
_cached_payload: dict[str, Any] | None = None


classify_public_http_status = homelab_probe_runner.classify_public_http_status


def internal_probes_enabled() -> bool:
    """Return whether internal TCP probes are explicitly enabled for this runtime."""
    return env_bool(_INTERNAL_PROBE_ENV)


_probe_http_endpoint = homelab_probe_runner.probe_http_endpoint


async def _probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    """Compatibility facade for public HTTP/Cloudflare probing."""
    return await homelab_probe_runner.probe_public_service(
        client,
        semaphore,
        service,
        http_probe=_probe_http_endpoint,
        edge_probe=_probe_http_edge_evidence,
    )


_probe_internal_service = partial(
    homelab_probe_runner.probe_internal_service,
    timeout_seconds=_INTERNAL_PROBE_TIMEOUT_SEC,
)


async def _collect_bounded_probe_batch(
    probes: list[tuple[HomelabService, asyncio.Task[dict[str, Any]]]],
    *,
    scope: Literal["public", "internal"],
    enabled: bool = True,
    eligible_count: int | None = None,
    per_probe_timeout_seconds: float = _PROBE_TIMEOUT_SEC,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compatibility facade preserving the module-level budget test seam."""
    return await homelab_probe_batch.collect_bounded_probe_batch(
        probes,
        scope=scope,
        enabled=enabled,
        eligible_count=eligible_count,
        per_probe_timeout_seconds=per_probe_timeout_seconds,
        fanout_budget_seconds=_SERVICE_FANOUT_BUDGET_SEC,
        max_concurrency=_MAX_PROBE_CONCURRENCY,
    )


_truenas_internal_target = truenas_probe_health.truenas_internal_target
_truenas_state = truenas_probe_health.truenas_state


async def _probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
) -> dict[str, Any]:
    return await probe_truenas(
        semaphore,
        internal_enabled=internal_enabled,
        http_probe=_probe_http_endpoint,
        internal_probe=_probe_internal_service,
    )


_copy_payload = partial(
    copy_homelab_health_payload,
    cache_ttl_seconds=_HEALTH_CACHE_TTL_SEC,
)

_BatchResult = tuple[list[dict[str, Any]], dict[str, Any]]


async def _run_refresh_probes(
    public_services: list[HomelabService],
    internal_services: list[HomelabService],
    *,
    public_eligible_count: int,
    internal_eligible_count: int,
    internal_enabled: bool,
) -> tuple[_BatchResult, dict[str, Any], _BatchResult]:
    """Run public, TrueNAS and internal probes concurrently under shared bounds."""
    service_semaphore = asyncio.Semaphore(_MAX_PROBE_CONCURRENCY)
    truenas_semaphore = asyncio.Semaphore(2)
    truenas_task = asyncio.create_task(
        _probe_truenas(
            truenas_semaphore,
            internal_enabled=internal_enabled,
        ),
    )
    internal_probe_tasks = [
        (
            service,
            asyncio.create_task(
                _probe_internal_service(service_semaphore, service),
            ),
        )
        for service in internal_services
    ]
    internal_results_task = asyncio.create_task(
        _collect_bounded_probe_batch(
            internal_probe_tasks,
            scope="internal",
            enabled=internal_enabled,
            eligible_count=internal_eligible_count,
            per_probe_timeout_seconds=_INTERNAL_PROBE_TIMEOUT_SEC,
        ),
    )

    timeout = httpx.Timeout(_PUBLIC_PROBE_TIMEOUT_SEC)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        # Observations must originate from this runtime, never an ambient proxy.
        trust_env=False,
    ) as client:
        public_probe_tasks = [
            (
                service,
                asyncio.create_task(
                    _probe_public_service(client, service_semaphore, service),
                ),
            )
            for service in public_services
        ]
        public_results_task = asyncio.create_task(
            _collect_bounded_probe_batch(
                public_probe_tasks,
                scope="public",
                eligible_count=public_eligible_count,
                per_probe_timeout_seconds=_PUBLIC_PROBE_TIMEOUT_SEC,
            ),
        )
        public_batch, truenas, internal_batch = await asyncio.gather(
            public_results_task,
            truenas_task,
            internal_results_task,
        )
    return public_batch, truenas, internal_batch


def _finalize_scope(
    scope: Literal["public", "internal"],
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    candidates: list[HomelabService],
    limit: int,
    enabled: bool,
    checked_at: str,
) -> list[dict[str, Any]]:
    """Merge retained evidence and attach sampling metadata to one probe scope."""
    merged = (
        merge_probe_evidence(
            scope,
            current_results=results,
            eligible_services=candidates,
            checked_at=checked_at,
        )
        if enabled
        else []
    )
    summary["evidence"] = evidence_summary(merged, eligible_count=len(candidates))
    summary["priority_source"] = _priority_source(candidates)
    summary["rotated_priority_ids"] = _rotated_priority_ids(candidates, limit=limit) if enabled else []
    return merged


def _catalog_coverage(
    services: list[HomelabService],
    public_candidates: list[HomelabService],
    internal_candidates: list[HomelabService],
) -> dict[str, int]:
    """Return catalogue coverage, distinct from rotating probe-slot coverage."""
    # Count unique services only; one may contribute public and LAN slots.
    monitored_ids = {service.service_id for service in (*public_candidates, *internal_candidates)}
    catalog_ids = {service.service_id for service in services}
    return {
        "catalog_service_count": len(services),
        "catalog_observable_service_count": len(catalog_ids & monitored_ids),
        "catalog_unconfigured_service_count": len(catalog_ids - monitored_ids),
    }


def _public_card_candidates(services: list[HomelabService]) -> list[dict[str, str]]:
    """Return curated public discovery names without private endpoint or probe evidence."""
    # Inventory does not attest that either service is available.
    public_labels = {"gatus": "Gatus", "garage-webui": "Garage Web UI"}
    return [{"id": service.service_id, "name": public_labels[service.service_id]} for service in services if service.service_id in public_labels and service.external is True]


async def build_homelab_health_payload(
    *,
    catalog_services: list[HomelabService] | None = None,
) -> dict[str, Any]:
    """Return bounded, cached homelab probes with explicit sampling metadata."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if _cached_payload is not None and (now - _cached_at) < _HEALTH_CACHE_TTL_SEC:
            return _copy_payload(
                _cached_payload,
                cache_source="memory",
                cache_age_seconds=now - _cached_at,
            )

        refresh_started = time.perf_counter()
        services = list(catalog_services) if catalog_services is not None else await fetch_homelab_services()
        public_candidates = [service for service in services if service.public_https_probe_url is not None]
        internal_candidates = [service for service in services if service.internal_host and service.internal_port is not None]
        internal_enabled = internal_probes_enabled()
        public_services = _select_probe_subset(
            public_candidates,
            limit=_MAX_PUBLIC_PROBES_PER_REFRESH,
        )
        internal_services = (
            _select_probe_subset(
                internal_candidates,
                limit=_MAX_INTERNAL_PROBES_PER_REFRESH,
            )
            if internal_enabled
            else []
        )

        (
            (public_results, public_summary),
            truenas,
            (internal_results, internal_summary),
        ) = await _run_refresh_probes(
            public_services,
            internal_services,
            public_eligible_count=len(public_candidates),
            internal_eligible_count=len(internal_candidates),
            internal_enabled=internal_enabled,
        )

        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        public_results = _finalize_scope(
            "public",
            public_results,
            public_summary,
            candidates=public_candidates,
            limit=_MAX_PUBLIC_PROBES_PER_REFRESH,
            enabled=True,
            checked_at=checked_at,
        )
        internal_results = _finalize_scope(
            "internal",
            internal_results,
            internal_summary,
            candidates=internal_candidates,
            limit=_MAX_INTERNAL_PROBES_PER_REFRESH,
            enabled=internal_enabled,
            checked_at=checked_at,
        )
        public_cards = _public_card_candidates(services)

        payload: dict[str, Any] = {
            "schema_version": 3,
            "checked_at": checked_at,
            "refresh_elapsed_ms": max(
                0,
                round((time.perf_counter() - refresh_started) * 1000),
            ),
            "truenas": truenas,
            "services": public_results,
            "public_probe_results": public_results,
            "public_card_candidates": public_cards,
            "internal_probes_enabled": internal_enabled,
            "internal_services": internal_results,
            "probe_summary": {
                "public": public_summary,
                "internal": internal_summary,
                **_catalog_coverage(services, public_candidates, internal_candidates),
                "internal_disabled_eligible_slots": (len(internal_candidates) if not internal_enabled else 0),
                "unsampled_current_window": {
                    "public": max(0, len(public_candidates) - len(public_services)),
                    "internal": (max(0, len(internal_candidates) - len(internal_services)) if internal_enabled else 0),
                },
                "sampling": {
                    "strategy": "priority-plus-rotating-window",
                    "cache_ttl_seconds": _HEALTH_CACHE_TTL_SEC,
                },
            },
        }
        _cached_payload = payload
        _cached_at = time.monotonic()
        return _copy_payload(
            payload,
            cache_source="origin",
            cache_age_seconds=0.0,
        )
