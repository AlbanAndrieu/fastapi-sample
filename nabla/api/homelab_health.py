# ruff: noqa: PLW0603 -- the module owns one lock-protected snapshot cache.

"""Cached health snapshots for rotating homelab service probes."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from nabla.api.homelab_catalog import fetch_homelab_services
from nabla.api.homelab_models import HomelabService
from nabla.api.homelab_probe_evidence import evidence_summary, merge_probe_evidence
from nabla.api.homelab_probe_policy import (
    HEALTH_CACHE_TTL_SEC as _HEALTH_CACHE_TTL_SEC,
    INTERNAL_PROBE_TIMEOUT_SEC as _INTERNAL_PROBE_TIMEOUT_SEC,
    MAX_INTERNAL_PROBES_PER_REFRESH as _MAX_INTERNAL_PROBES_PER_REFRESH,
    MAX_PROBE_CONCURRENCY as _MAX_PROBE_CONCURRENCY,
    MAX_PUBLIC_PROBES_PER_REFRESH as _MAX_PUBLIC_PROBES_PER_REFRESH,
    PUBLIC_PROBE_TIMEOUT_SEC as _PUBLIC_PROBE_TIMEOUT_SEC,
    select_probe_subset as _select_probe_subset,
)
from nabla.api.homelab_probe_runner import (
    _collect_bounded_probe_batch,
    _probe_http_endpoint,
    _probe_internal_service,
    _probe_public_service as _run_public_service_probe,
    classify_public_http_status,
    internal_probes_enabled,
)
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.api.sickz_cloudflare_edge import _probe_http_edge_evidence
from nabla.api.truenas_diagnostics import (
    append_truenas_api_stages,
    collect_truenas_network_diagnostics,
    unmeasured_truenas_network_diagnostics,
)
from nabla.api.truenas_health_observer import (
    observe_truenas_health_api as _observe_truenas_api,
    truenas_http_verify_ssl,
)
from nabla.integrations.truenas_client import (
    TrueNASSettings,
    truenas_host_port,
    truenas_url,
)

HealthState = Literal["ok", "warn", "fail"]
_PROBE_TIMEOUT_SEC = 5.0
_TRUENAS_DIAGNOSTICS_BUDGET_SEC = 3.0
_cache_lock = asyncio.Lock()
_cached_at = 0.0
_cached_payload: dict[str, Any] | None = None


async def _probe_public_service(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    service: HomelabService,
) -> dict[str, Any]:
    """Compatibility wrapper retaining monkeypatchable Cloudflare edge evidence."""
    result = await _run_public_service_probe(client, semaphore, service)
    if (
        not service.effective_cloudflare_access_required
        or result.get("http_status") not in {401, 403, 407, 429}
    ):
        return result

    # The extracted runner uses the same default edge probe in production. Tests
    # and diagnostics historically monkeypatch this module-level symbol, so keep
    # that contract explicit rather than coupling tests to the helper module.
    edge_evidence = await _probe_http_edge_evidence(service.public_https_probe_url or "")
    result.update(edge_evidence)
    if edge_evidence.get("cloudflare_service_token_access_passed") is not True:
        return result
    authenticated_status = int(
        edge_evidence.get("cloudflare_service_token_http_status") or 0
    )
    result["anonymous_http_status"] = result["http_status"]
    result["http_status"] = authenticated_status
    result["state"] = classify_public_http_status(authenticated_status)
    result["reachable"] = authenticated_status > 0
    result["public_probe_auth_mode"] = "cloudflare_service_token"
    return result


def _truenas_internal_target(
    _services: list[HomelabService] | None = None,
) -> tuple[str, int]:
    return truenas_host_port()


def _truenas_state(
    public_result: dict[str, Any],
    internal_result: dict[str, Any] | None,
    api_result: dict[str, Any] | None = None,
) -> HealthState:
    """Resolve TrueNAS with fresh API evidence before path evidence."""
    public_state = public_result.get("state")
    internal_state = internal_result.get("state") if internal_result else None
    api_reachable = api_result.get("reachable") if api_result else None
    api_stale = bool(api_result and api_result.get("stale"))
    if api_reachable is False and not api_stale:
        return "fail"
    if api_reachable is False and api_stale:
        return "warn"
    if public_state == "fail" and (internal_state == "ok" or api_reachable is True):
        return "warn"
    if public_state == "fail":
        return "fail"
    if internal_state == "fail":
        return "warn"
    if public_state == "warn":
        return "warn"
    return "ok"


async def _probe_truenas(
    semaphore: asyncio.Semaphore,
    *,
    internal_enabled: bool,
) -> dict[str, Any]:
    """Probe TrueNAS while overlapping HTTPS, API, TCP and path diagnostics."""
    configured_url = truenas_url().rstrip("/") + "/"
    api_task = asyncio.create_task(_observe_truenas_api())
    internal_task: asyncio.Task[dict[str, Any]] | None = None
    if internal_enabled:
        host, port = _truenas_internal_target()
        internal_task = asyncio.create_task(
            _probe_internal_service(
                semaphore,
                HomelabService(
                    name="TrueNAS TCP",
                    internalHost=host,
                    internalPort=port,
                    external=False,
                ),
            )
        )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_PROBE_TIMEOUT_SEC),
        follow_redirects=False,
        verify=truenas_http_verify_ssl(),
    ) as truenas_client:
        public_result = await _probe_http_endpoint(
            truenas_client,
            semaphore,
            service_id="truenas",
            name="TrueNAS HTTPS",
            url=configured_url,
        )

    host, port = truenas_host_port()
    verify_ssl = truenas_http_verify_ssl()
    ws_path = os.getenv("TRUENAS_WS_PATH", "/api/current").strip() or "/api/current"
    websocket_uri = TrueNASSettings(
        url=truenas_url(),
        verify_ssl=verify_ssl,
        websocket_path=ws_path,
    ).websocket_uri
    path_mode = "direct_lan" if homelab_runtime_detected() else "public_wan_haproxy"
    diagnostics_task = asyncio.create_task(
        collect_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            public_result=public_result,
            path_mode=path_mode,
        )
    )

    api_result = await api_task
    internal_result = await internal_task if internal_task is not None else None
    try:
        diagnostics = await asyncio.wait_for(
            diagnostics_task,
            timeout=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    except TimeoutError:
        diagnostics_task.cancel()
        await asyncio.gather(diagnostics_task, return_exceptions=True)
        diagnostics = unmeasured_truenas_network_diagnostics(
            host=host,
            port=port,
            websocket_uri=websocket_uri,
            verify_ssl=verify_ssl,
            path_mode=path_mode,
            budget_seconds=_TRUENAS_DIAGNOSTICS_BUDGET_SEC,
        )
    diagnostics = append_truenas_api_stages(diagnostics, api_result)
    return {
        "id": "truenas",
        "state": _truenas_state(public_result, internal_result, api_result),
        "public": public_result,
        "internal": internal_result,
        "api": api_result,
        "diagnostics": diagnostics,
        "internal_probe_enabled": internal_enabled,
        "verify_ssl": verify_ssl,
    }


def _copy_payload(
    payload: dict[str, Any],
    *,
    cache_source: Literal["origin", "memory"],
    cache_age_seconds: float,
) -> dict[str, Any]:
    truenas = payload.get("truenas")
    truenas_copy = None
    if isinstance(truenas, dict):
        truenas_copy = {
            **truenas,
            **{
                key: dict(value) if isinstance(value, dict) else value
                for key in ("public", "internal", "api")
                if (value := truenas.get(key)) is not None
            },
        }
    raw_summary = payload.get("probe_summary") or {}
    probe_summary = dict(raw_summary)
    for scope in ("public", "internal"):
        if isinstance(raw_summary.get(scope), dict):
            probe_summary[scope] = dict(raw_summary[scope])
    age = max(0.0, cache_age_seconds)
    return {
        **payload,
        "truenas": truenas_copy,
        "services": [dict(service) for service in payload.get("services", [])],
        "public_probe_results": [
            dict(service) for service in payload.get("public_probe_results", [])
        ],
        "internal_services": [
            dict(service) for service in payload.get("internal_services", [])
        ],
        "probe_summary": probe_summary,
        "probe_cache": {
            "source": cache_source,
            "age_seconds": round(age, 3),
            "ttl_seconds": _HEALTH_CACHE_TTL_SEC,
            "stale": age >= _HEALTH_CACHE_TTL_SEC,
        },
    }


async def build_homelab_health_payload(
    *,
    catalog_services: list[HomelabService] | None = None,
) -> dict[str, Any]:
    """Return bounded, cached probes with rotating sampling metadata."""
    global _cached_at, _cached_payload

    async with _cache_lock:
        now = time.monotonic()
        if _cached_payload is not None and now - _cached_at < _HEALTH_CACHE_TTL_SEC:
            return _copy_payload(
                _cached_payload,
                cache_source="memory",
                cache_age_seconds=now - _cached_at,
            )

        refresh_started = time.perf_counter()
        services = (
            list(catalog_services)
            if catalog_services is not None
            else await fetch_homelab_services()
        )
        public_candidates = [
            service for service in services if service.public_https_probe_url is not None
        ]
        internal_candidates = [
            service
            for service in services
            if service.internal_host and service.internal_port is not None
        ]
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

        service_semaphore = asyncio.Semaphore(_MAX_PROBE_CONCURRENCY)
        truenas_task = asyncio.create_task(
            _probe_truenas(asyncio.Semaphore(2), internal_enabled=internal_enabled)
        )
        internal_results_task = asyncio.create_task(
            _collect_bounded_probe_batch(
                [
                    (
                        service,
                        asyncio.create_task(
                            _probe_internal_service(service_semaphore, service)
                        ),
                    )
                    for service in internal_services
                ],
                scope="internal",
                enabled=internal_enabled,
                eligible_count=len(internal_candidates),
                per_probe_timeout_seconds=_INTERNAL_PROBE_TIMEOUT_SEC,
            )
        )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_PUBLIC_PROBE_TIMEOUT_SEC),
            follow_redirects=False,
        ) as client:
            public_results_task = asyncio.create_task(
                _collect_bounded_probe_batch(
                    [
                        (
                            service,
                            asyncio.create_task(
                                _probe_public_service(client, service_semaphore, service)
                            ),
                        )
                        for service in public_services
                    ],
                    scope="public",
                    eligible_count=len(public_candidates),
                    per_probe_timeout_seconds=_PUBLIC_PROBE_TIMEOUT_SEC,
                )
            )
            (public_results, public_summary), truenas, (
                internal_results,
                internal_summary,
            ) = await asyncio.gather(
                public_results_task,
                truenas_task,
                internal_results_task,
            )

        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        public_results = merge_probe_evidence(
            "public",
            current_results=public_results,
            eligible_services=public_candidates,
            checked_at=checked_at,
        )
        internal_results = (
            merge_probe_evidence(
                "internal",
                current_results=internal_results,
                eligible_services=internal_candidates,
                checked_at=checked_at,
            )
            if internal_enabled
            else []
        )
        public_summary["evidence"] = evidence_summary(
            public_results,
            eligible_count=len(public_candidates),
        )
        internal_summary["evidence"] = evidence_summary(
            internal_results,
            eligible_count=len(internal_candidates),
        )

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
            "internal_probes_enabled": internal_enabled,
            "internal_services": internal_results,
            "probe_summary": {
                "public": public_summary,
                "internal": internal_summary,
                "catalog_service_count": len(services),
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
