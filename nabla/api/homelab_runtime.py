# ruff: noqa: PLW0603 -- cache state is intentionally process-local.
"""TrueNAS runtime observation and reconciliation with code-owned declarations."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nabla.api.homelab_declared import (
    DeclaredService,
    RuntimeBinding,
    fetch_declared_service_catalog,
)
from nabla.integrations.truenas_client import build_truenas_adapter

ReconciliationState = Literal[
    "in_sync",
    "declared_only",
    "observed_only",
    "binding_conflict",
    "runtime_unknown",
    "not_observed",
]

_DEFAULT_RUNTIME_CACHE_TTL_SECONDS = 30.0
_TRUENAS_RESET_RETRY_DELAY_SECONDS = 0.2
_TRUENAS_MAX_ATTEMPTS = 3
_RUNTIME_CACHE_LOCK = threading.Lock()
_RUNTIME_CACHE: TrueNASRuntimeSnapshot | None = None
_RUNTIME_CACHE_EXPIRES_AT = 0.0


class ObservedContainer(BaseModel):
    """One container reported by TrueNAS active_workloads."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    service_name: str | None = None
    image: str | None = None
    state: str | None = None


class ObservedApp(BaseModel):
    """One installed TrueNAS App with the runtime facts needed for reconciliation."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    app_id: str
    name: str
    state: str = "UNKNOWN"
    version: str | None = None
    human_version: str | None = None
    upgrade_available: bool = False
    containers: list[ObservedContainer] = Field(default_factory=list)


class TrueNASRuntimeSnapshot(BaseModel):
    """Read-only sanitized snapshot returned to homelab consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["truenas"] = "truenas"
    observed_at: str
    configured: bool
    reachable: bool
    stale: bool = False
    apps: list[ObservedApp] = Field(default_factory=list)
    error: str | None = None


def _short_error(exc: BaseException) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:240]


def _runtime_cache_ttl_seconds() -> float:
    """Return a bounded cache TTL so configuration mistakes cannot cache indefinitely."""
    raw = os.getenv("TRUENAS_RUNTIME_CACHE_TTL_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_RUNTIME_CACHE_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_RUNTIME_CACHE_TTL_SECONDS
    return max(5.0, min(value, 300.0))


def _observed_app(raw: dict[str, Any]) -> ObservedApp:
    workloads = raw.get("active_workloads") or {}
    raw_containers = workloads.get("container_details") or []
    containers = [
        ObservedContainer(
            service_name=(str(container.get("service_name")) if container.get("service_name") is not None else None),
            image=(str(container.get("image")) if container.get("image") is not None else None),
            state=(str(container.get("state")) if container.get("state") is not None else None),
        )
        for container in raw_containers
        if isinstance(container, dict)
    ]
    app_id = str(raw.get("id") or raw.get("name") or "unknown")
    return ObservedApp(
        app_id=app_id,
        name=str(raw.get("name") or app_id),
        state=str(raw.get("state") or raw.get("status") or "UNKNOWN"),
        version=str(raw["version"]) if raw.get("version") is not None else None,
        human_version=(str(raw["human_version"]) if raw.get("human_version") is not None else None),
        upgrade_available=bool(raw.get("upgrade_available", False)),
        containers=containers,
    )


def _list_apps_with_reset_retry(adapter: Any) -> list[dict[str, Any]]:
    """Retry bounded transient peer resets without hiding persistent failures."""
    for attempt in range(1, _TRUENAS_MAX_ATTEMPTS + 1):
        try:
            return adapter.list_apps()
        except Exception as exc:
            transient = (
                isinstance(
                    exc,
                    (ConnectionError, TimeoutError),
                )
                or "timeout" in exc.__class__.__name__.casefold()
            )
            if not transient or attempt == _TRUENAS_MAX_ATTEMPTS:
                raise
            time.sleep(_TRUENAS_RESET_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError("unreachable TrueNAS retry state")


def observe_truenas_runtime() -> TrueNASRuntimeSnapshot:
    """Read app.query through the official client without exposing credentials."""
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    adapter = build_truenas_adapter()
    if adapter is None:
        return TrueNASRuntimeSnapshot(
            observed_at=observed_at,
            configured=False,
            reachable=False,
            error="TrueNAS API credentials are not configured",
        )
    try:
        apps = [_observed_app(app) for app in _list_apps_with_reset_retry(adapter)]
    except Exception as exc:
        return TrueNASRuntimeSnapshot(
            observed_at=observed_at,
            configured=True,
            reachable=False,
            error=_short_error(exc),
        )
    return TrueNASRuntimeSnapshot(
        observed_at=observed_at,
        configured=True,
        reachable=True,
        apps=apps,
    )


def _cached_truenas_runtime() -> TrueNASRuntimeSnapshot:
    """Share one TrueNAS observation across callers and retain the last known good snapshot."""
    global _RUNTIME_CACHE, _RUNTIME_CACHE_EXPIRES_AT

    now = time.monotonic()
    with _RUNTIME_CACHE_LOCK:
        if _RUNTIME_CACHE is not None and now < _RUNTIME_CACHE_EXPIRES_AT:
            return _RUNTIME_CACHE

        previous = _RUNTIME_CACHE
        refreshed = observe_truenas_runtime()
        ttl = _runtime_cache_ttl_seconds()
        _RUNTIME_CACHE_EXPIRES_AT = time.monotonic() + ttl

        if refreshed.reachable or previous is None or not previous.reachable:
            _RUNTIME_CACHE = refreshed
            return refreshed

        stale = previous.model_copy(
            update={
                "stale": True,
                "error": refreshed.error or "TrueNAS refresh failed; serving last known good snapshot",
            },
        )
        _RUNTIME_CACHE = stale
        return stale


def _reset_runtime_cache() -> None:
    """Reset module cache for deterministic tests."""
    global _RUNTIME_CACHE, _RUNTIME_CACHE_EXPIRES_AT
    with _RUNTIME_CACHE_LOCK:
        _RUNTIME_CACHE = None
        _RUNTIME_CACHE_EXPIRES_AT = 0.0


async def fetch_truenas_runtime() -> TrueNASRuntimeSnapshot:
    """Return the shared runtime snapshot without blocking the ASGI event loop."""
    return await asyncio.to_thread(_cached_truenas_runtime)


def match_runtime_binding(
    app: ObservedApp,
    binding: RuntimeBinding,
) -> tuple[bool, ObservedContainer | None]:
    app_identity_matched = False
    if binding.app_id:
        app_identity_matched = app.app_id == binding.app_id or app.name == binding.app_id
        if not app_identity_matched:
            return False, None
    if not binding.container_service:
        return True, None

    matches = [container for container in app.containers if container.service_name == binding.container_service]
    if matches:
        return True, matches[0]

    # A stopped TrueNAS App may expose no active_workloads/container details.
    # When appId already matched exactly, retain that stronger runtime identity
    # rather than splitting one stopped App into declared_only + observed_only.
    if app_identity_matched and not app.containers:
        return True, None
    return False, None


def _reconcile_declared(
    service: DeclaredService,
    snapshot: TrueNASRuntimeSnapshot,
) -> tuple[dict[str, Any], set[str]]:
    binding = service.runtime
    base: dict[str, Any] = {
        "id": service.service_id,
        "name": service.name,
        "declared": True,
        "sourcePath": service.source_path,
        "composeService": service.compose_service,
        "runtimeBinding": (binding.model_dump(mode="json", by_alias=True, exclude_none=True) if binding is not None else None),
    }
    if binding is None or binding.provider != "truenas-app":
        return {**base, "reconciliation": "not_observed"}, set()
    if not snapshot.reachable:
        return {**base, "reconciliation": "runtime_unknown"}, set()

    matches: list[tuple[ObservedApp, ObservedContainer | None]] = []
    for app in snapshot.apps:
        matched, container = match_runtime_binding(app, binding)
        if matched:
            matches.append((app, container))
    if not matches:
        return {**base, "reconciliation": "declared_only"}, set()
    if len(matches) > 1:
        return {
            **base,
            "reconciliation": "binding_conflict",
            "matchingApps": [app.app_id for app, _ in matches],
        }, {app.app_id for app, _ in matches}

    app, container = matches[0]
    observed: dict[str, Any] = {
        "appId": app.app_id,
        "appName": app.name,
        "appState": app.state,
        "version": app.version,
        "humanVersion": app.human_version,
        "upgradeAvailable": app.upgrade_available,
    }
    if container is not None:
        observed["container"] = container.model_dump(exclude_none=True)
    return {
        **base,
        "reconciliation": "in_sync",
        "observed": observed,
    }, {app.app_id}


async def _catalog_membership_drift(
    declared_services: list[DeclaredService],
) -> dict[str, Any]:
    """Compare presentation, declared-runtime and topology membership without failing status."""
    from nabla.api.homelab_catalog import fetch_homelab_catalog
    from nabla.api.homelab_topology import fetch_homelab_topology

    try:
        presentation, topology = await asyncio.gather(
            fetch_homelab_catalog(),
            fetch_homelab_topology(),
        )
    except Exception as exc:  # pragma: no cover - remote catalog/provider dependent
        return {
            "available": False,
            "error": _short_error(exc),
            "services": [],
        }

    presentation_by_id = {
        service.service_id: service.name for service in presentation.services
    }
    declared_by_id = {service.service_id: service.name for service in declared_services}
    topology_by_id = {node.id: node.name for node in topology.nodes}
    service_ids = sorted(
        set(presentation_by_id) | set(declared_by_id) | set(topology_by_id),
    )
    drift = []
    for service_id in service_ids:
        membership = {
            "presentation": service_id in presentation_by_id,
            "declared": service_id in declared_by_id,
            "topology": service_id in topology_by_id,
        }
        if len(set(membership.values())) == 1:
            continue
        drift.append(
            {
                "id": service_id,
                "name": (
                    presentation_by_id.get(service_id)
                    or declared_by_id.get(service_id)
                    or topology_by_id.get(service_id)
                    or service_id
                ),
                **membership,
            },
        )

    return {
        "available": True,
        "presentationCount": len(presentation_by_id),
        "declaredCount": len(declared_by_id),
        "topologyCount": len(topology_by_id),
        "driftCount": len(drift),
        "services": drift,
    }


async def build_homelab_status_payload() -> dict[str, Any]:
    """Join declared services with TrueNAS runtime and surface configuration drift."""
    catalog_task = asyncio.create_task(fetch_declared_service_catalog())
    runtime_task = asyncio.create_task(fetch_truenas_runtime())
    catalog, runtime = await asyncio.gather(catalog_task, runtime_task)
    catalog_drift = await _catalog_membership_drift(catalog.services)

    rows: list[dict[str, Any]] = []
    matched_app_ids: set[str] = set()
    for service in catalog.services:
        row, app_ids = _reconcile_declared(service, runtime)
        rows.append(row)
        matched_app_ids.update(app_ids)

    observed_only = [
        {
            "id": f"truenas:{app.app_id}",
            "name": app.name,
            "declared": False,
            "reconciliation": "observed_only",
            "observed": {
                "appId": app.app_id,
                "appName": app.name,
                "appState": app.state,
                "version": app.version,
                "humanVersion": app.human_version,
                "upgradeAvailable": app.upgrade_available,
                "containers": [container.model_dump(exclude_none=True) for container in app.containers],
            },
        }
        for app in runtime.apps
        if app.app_id not in matched_app_ids
    ]

    reconciliation_counts = {
        state: sum(1 for row in rows if row.get("reconciliation") == state)
        for state in (
            "in_sync",
            "declared_only",
            "binding_conflict",
            "runtime_unknown",
            "not_observed",
        )
    }
    drift_summary = {
        "inSync": reconciliation_counts["in_sync"],
        "declaredOnly": reconciliation_counts["declared_only"],
        "bindingConflicts": reconciliation_counts["binding_conflict"],
        "runtimeUnknown": reconciliation_counts["runtime_unknown"],
        "notObserved": reconciliation_counts["not_observed"],
        "observedOnly": len(observed_only),
        "hasDrift": bool(
            reconciliation_counts["declared_only"]
            or reconciliation_counts["binding_conflict"]
            or observed_only,
        ),
    }

    return {
        "schemaVersion": 1,
        "checkedAt": runtime.observed_at,
        "catalogRevision": catalog.catalog_revision,
        "topologyVersion": catalog.topology_version,
        "runtime": runtime.model_dump(mode="json", exclude_none=True),
        "services": rows,
        "observedOnly": observed_only,
        "driftSummary": drift_summary,
        "catalogDrift": catalog_drift,
    }
