# ruff: noqa: PLC0415 -- route-local imports keep optional probes lazy.

"""Health and homelab route registration.

Keep dependency probes and diagnostic endpoints isolated from the general application
route module. The public paths and response contracts intentionally remain unchanged.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import pyroscope
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from nabla.api.homelab_declared import DeclaredServiceCatalog
from nabla.api.homelab_runtime import TrueNASRuntimeSnapshot
from nabla.api.homelab_topology import HomelabTopology
from nabla.api.owner_ui_session import owner_ui_authenticated
from nabla.api.platform_health_diagnostics import utc_now
from nabla.api.probe_runtime import probe_runtime_metadata
from nabla.api.public_homelab_dto import PublicHomelabV1, load_public_homelab_v1
from nabla.api.site_architecture_catalog import (
    SiteArchitectureCatalogV2,
    SiteCatalogV2Unavailable,
    fetch_site_catalog_v2,
)
from nabla.api.site_health_v2 import SiteHealthV2, fetch_site_health_v2
from nabla.api.site_trace_context import verified_site_trace_id
from nabla.api.ui_public_services import (
    PublicUiServices,
    get_public_ui_services,
    public_ui_services_enabled,
)
from nabla.config_settings import get_settings
from nabla.diagnostics_readonly_mode import public_diagnostics_readonly_enabled
from nabla.utils.logger import logger


_NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}
_PRIVATE_NO_STORE_HEADERS = {**_NO_STORE_HEADERS, "X-Robots-Tag": "noindex, nofollow"}


def _legacy_homelab_http_enabled() -> bool:
    """Migration switch: only HTTP v1 serialization, never internal probes."""
    return os.getenv("HOMELAB_V1_HTTP_ENABLED", "true").strip().lower() == "true"


def _register_site_catalog_routes(app: FastAPI) -> None:
    """Register curated public labels and the sanitized site catalog v2."""

    @app.get(
        "/api/public-homelab/v1",
        response_model=PublicHomelabV1,
        tags=["Homelab"],
        summary="Explicitly allowlisted public service labels",
    )
    async def get_public_homelab_v1(response: Response) -> PublicHomelabV1:
        """Return only curated labels; never fetch or serialize runtime data."""
        if not _legacy_homelab_http_enabled():
            raise HTTPException(status_code=410, detail="Legacy public catalog retired")
        response.headers.update(
            {
                "Cache-Control": "public, max-age=60",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )
        return load_public_homelab_v1()

    @app.get(
        "/api/site/catalog/v2",
        response_model=SiteArchitectureCatalogV2,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="Authenticated sanitized site architecture catalog",
        include_in_schema=False,
    )
    async def get_site_architecture_catalog(response: Response) -> SiteArchitectureCatalogV2:
        """Only the current verified Backstage v2 source, safely projected."""

        response.headers.update(_PRIVATE_NO_STORE_HEADERS)
        try:
            return await fetch_site_catalog_v2()
        except SiteCatalogV2Unavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Authoritative catalog unavailable",
                headers={**_PRIVATE_NO_STORE_HEADERS, "X-Nabla-Diagnostic-Stage": exc.stage},
            ) from None


def _register_site_status_routes(app: FastAPI) -> None:
    """Register the machine site health v2 and the minimal public UI feed."""

    @app.get(
        "/api/site/health/v2",
        response_model=SiteHealthV2,
        summary="Machine-authenticated minimal v2 service states",
        tags=["Homelab"],
        include_in_schema=False,
    )
    async def get_site_health_v2(request: Request, response: Response) -> SiteHealthV2:
        trace_id = verified_site_trace_id(request.headers.get("traceparent"))
        response.headers.update(_PRIVATE_NO_STORE_HEADERS)
        if trace_id:
            response.headers["X-Nabla-Trace-ID"] = trace_id
            logger.info("site_health_v2", trace_id=trace_id)
        try:
            return await fetch_site_health_v2(request)
        except SiteCatalogV2Unavailable:
            raise HTTPException(
                status_code=503,
                detail="Authoritative Backstage v2 unavailable",
                headers={**_NO_STORE_HEADERS, **({"X-Nabla-Trace-ID": trace_id} if trace_id else {})},
            ) from None

    @app.get(
        "/api/ui/services",
        response_model=PublicUiServices,
        tags=["Homelab"],
        include_in_schema=False,
    )
    async def get_public_service_overview(request: Request, response: Response) -> PublicUiServices:
        """Temporary minimal UI feed. Raw diagnostics stay owner-only."""
        if not public_ui_services_enabled():
            raise HTTPException(status_code=404, detail="Not found")
        response.headers.update(_PRIVATE_NO_STORE_HEADERS)
        try:
            return await get_public_ui_services(request)
        except SiteCatalogV2Unavailable:
            raise HTTPException(
                status_code=503,
                detail="Service overview temporarily unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None


def _register_homelab_catalog_routes(app: FastAPI) -> None:
    """Register declared catalog, topology and runtime inventory routes."""
    _register_site_catalog_routes(app)
    _register_site_status_routes(app)

    @app.get(
        "/api/homelab-services",
        tags=["Homelab"],
        summary="Deprecated route view of the Backstage v2 exposure intent",
    )
    async def get_homelab_services() -> dict[str, Any]:
        """Compatibility read for the deployed Site until it reads /api/site/catalog/v2.

        Projected from Backstage v2 route intent only; delete with this endpoint
        once the Site Alban v2 PR is merged.
        """
        if not _legacy_homelab_http_enabled():
            raise HTTPException(status_code=410, detail="Legacy catalog retired")
        from nabla.api.catalog_routes import fetch_catalog_routes

        services = []
        for route in await fetch_catalog_routes():
            row = {
                "id": route.service_id,
                "entityRef": route.entity_ref,
                "route": route.route,
                "name": route.name,
                "description": route.description,
                "external": route.public,
                "tunnelUrl": route.url,
                "tunnelSecure": route.cloudflare_edge,
                "cloudflareAccessRequired": route.access_required,
                "healthPath": route.probe_path,
                "securityException": route.risk_reason,
                "internalHost": route.backend_host,
                "internalPort": route.backend_port,
                "internalSecure": route.backend_tls,
            }
            services.append({key: value for key, value in row.items() if value is not None})
        return {"version": 2, "services": services}

    @app.get(
        "/api/homelab/declared-services",
        response_model=DeclaredServiceCatalog,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="Code-owned declared homelab services",
    )
    async def get_declared_homelab_services() -> DeclaredServiceCatalog:
        """Expose the service inventory generated from nabla-compose x-nabla metadata."""
        from nabla.api.homelab_declared import fetch_declared_service_catalog

        return await fetch_declared_service_catalog()

    @app.get(
        "/api/public-topology",
        tags=["Homelab"],
        summary="Sanitized public homelab topology",
        include_in_schema=False,
    )
    async def get_public_homelab_topology(response: Response) -> dict[str, object]:
        """Expose logical topology without internal URLs, ports or source evidence."""
        from nabla.api.homelab_topology import (
            fetch_homelab_topology,
            public_topology_payload,
        )

        response.headers.update(_NO_STORE_HEADERS)
        return public_topology_payload(await fetch_homelab_topology())

    @app.get(
        "/api/homelab-topology",
        response_model=HomelabTopology,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="Declared homelab service topology",
    )
    async def get_homelab_topology() -> HomelabTopology:
        """Expose the validated design-time topology sourced from nabla-compose."""
        from nabla.api.homelab_topology import fetch_homelab_topology

        return await fetch_homelab_topology()

    @app.get(
        "/api/homelab/runtime",
        response_model=TrueNASRuntimeSnapshot,
        response_model_exclude_none=True,
        tags=["Homelab", "TrueNAS"],
        summary="Observed TrueNAS application runtime",
    )
    async def get_homelab_runtime() -> TrueNASRuntimeSnapshot:
        """Expose a sanitized app.query snapshot from the official TrueNAS client."""
        from nabla.api.homelab_runtime import fetch_truenas_runtime

        return await fetch_truenas_runtime()


def _register_homelab_health_routes(app: FastAPI) -> None:
    """Register homelab status, health, probe and runtime-topology routes."""

    @app.get(
        "/api/homelab/status",
        tags=["Homelab", "TrueNAS"],
        summary="Declared versus observed homelab status",
    )
    async def get_homelab_status() -> dict[str, Any]:
        """Reconcile declarations/runtime and expose provider credential presence only."""
        from nabla.api.homelab_runtime import build_homelab_status_payload
        from nabla.api.provider_credentials import infrastructure_provider_credentials

        payload = await build_homelab_status_payload()
        payload["providerCredentials"] = infrastructure_provider_credentials()
        return payload

    @app.get(
        "/api/homelab/health",
        tags=["Homelab", "Health"],
        summary="Homelab and platform health",
    )
    async def get_homelab_health() -> dict[str, Any]:
        """Return detailed homelab services plus shared core/platform components."""
        from nabla.api.health_board import build_homelab_snapshot

        return await build_homelab_snapshot()

    @app.get(
        "/api/homelab/probes",
        tags=["Homelab", "Health", "TrueNAS"],
        summary="Bounded low-level homelab probe matrix",
    )
    async def get_homelab_probes(response: Response) -> dict[str, Any]:
        """Expose bounded raw probes without waiting for aggregate reconciliation."""
        from nabla.api.homelab_health import build_homelab_health_payload

        response.headers.update(_NO_STORE_HEADERS)
        payload = dict(await build_homelab_health_payload())
        payload["probe_runtime"] = probe_runtime_metadata(payload)
        return payload

    @app.get(
        "/api/runtime/topology",
        tags=["Health", "Runtime"],
        summary="Observed application runtimes and public egress",
    )
    async def get_runtime_topology(request: Request, response: Response) -> dict[str, Any]:
        """Expose sanitized cross-replica heartbeat and egress evidence."""
        from nabla.api.runtime_topology import build_runtime_topology_snapshot
        from nabla.app_features import features_from_state

        features = features_from_state(request.app.state)
        if features.redis:
            from nabla.api.demo.socket.redis import redis
        else:
            redis = None

        response.headers.update(_NO_STORE_HEADERS)
        return await build_runtime_topology_snapshot(
            redis,
            hostname=request.url.hostname,
            features=features,
        )


def _register_probe_routes(app: FastAPI) -> None:
    """Register liveness, readiness and deep health probe routes."""

    @app.get(
        "/livez",
        tags=["Health"],
        summary="Process liveness without dependency I/O",
        operation_id="get_liveness",
    )
    async def get_liveness(response: Response) -> dict[str, Any]:
        from nabla.api.health_contracts import build_liveness_payload

        response.headers.update(_NO_STORE_HEADERS)
        return build_liveness_payload(version=app.version)

    @app.get(
        "/readyz",
        tags=["Health"],
        summary="Readiness of traffic-critical dependencies",
        operation_id="get_readiness",
    )
    async def get_readiness(request: Request) -> JSONResponse:
        from nabla.api.health_contracts import build_readiness_payload
        from nabla.app_features import features_from_state

        features = features_from_state(request.app.state)
        engine = redis = None
        if features.database:
            from nabla.api.db.database import engine
        if features.redis:
            from nabla.api.demo.socket.redis import redis

        payload, ready = await build_readiness_payload(
            redis_client=redis,
            engine=engine,
            version=app.version,
            features=features,
        )
        return JSONResponse(
            payload,
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            headers=_NO_STORE_HEADERS,
        )

    @app.get(
        "/healthz",
        tags=["Health"],
        summary="Deep healthcheck",
    )
    async def get_healthz(request: Request, response: Response) -> dict[str, Any]:
        """Return runtime health plus deep dependency and service probes."""
        from nabla.api.health_board import build_extended_healthz

        response.headers.update(_NO_STORE_HEADERS)
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_extended_healthz(request)

    @app.get(
        "/sickz",
        tags=["Health"],
        summary="Exposure security policy",
    )
    async def get_sickz(request: Request, response: Response) -> dict[str, Any]:
        """Compare declared external/Cloudflare policy with observed reachability."""
        from nabla.api.health_board import build_sickz_snapshot
        from nabla.api.sickz_cache import cached_sickz_snapshot

        response.headers.update(_NO_STORE_HEADERS)
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await cached_sickz_snapshot(request, build_sickz_snapshot)


def _register_health_board_routes(app: FastAPI) -> None:
    """Register health-board cache, refresh-event and Sentry debug routes."""

    @app.get(
        "/api/health-board",
        tags=["Health"],
        summary="Cached aggregate used by the public health board",
        operation_id="get_health_board_snapshot",
    )
    async def get_health_board(
        request: Request,
        response: Response,
        force_refresh: Annotated[bool, Query(alias="refresh")] = False,
    ) -> dict[str, Any]:
        from nabla.api.health_board import get_health_board_snapshot

        response.headers.update(_NO_STORE_HEADERS)
        # Anonymous readers can observe the cache, but must not force expensive
        # outbound probes on every request. Normal stale refresh still runs.
        if force_refresh and public_diagnostics_readonly_enabled():
            force_refresh = owner_ui_authenticated(request, get_settings())
        return await get_health_board_snapshot(
            request,
            force_refresh=force_refresh,
        )

    @app.post(
        "/api/health-board/cache/reset",
        include_in_schema=False,
    )
    async def reset_health_probe_caches(response: Response) -> dict[str, Any]:
        """Purge shared provider probe caches/circuits and the aggregate health board."""
        from nabla.api.external_probe_cache import reset_probe_cache
        from nabla.api.external_probe_cache_redis import resolve_redis_client
        from nabla.api.health_board import reset_health_board_cache
        from nabla.api.sickz_cache import reset_sickz_cache

        probe_keys = (
            "pfsense:liveness",
            "pfsense:posture",
            "pfsense:snort2c",
            "truenas:api",
            "cloudflare:tunnels",
            "cloudflare:exposure",
        )
        redis_client = resolve_redis_client()
        for key in probe_keys:
            await reset_probe_cache(key, redis_client=redis_client)
        await reset_health_board_cache()
        await reset_sickz_cache()
        response.headers.update(_NO_STORE_HEADERS)
        logger.info("health_probe_cache_reset keys=%s", len(probe_keys))
        return {
            "reset": True,
            "probe_keys": list(probe_keys),
            "reset_at": utc_now(),
        }

    @app.post(
        "/api/health-board/refresh-event",
        include_in_schema=False,
        status_code=204,
    )
    async def log_health_board_refresh(request: Request) -> Response:
        """Record an explicit UI refresh click for FastAPI Cloud runtime diagnostics."""
        logger.info(
            "health_board_refresh clicked referer=%s user_agent=%s",
            request.headers.get("referer", "-"),
            request.headers.get("user-agent", "-"),
        )
        return Response(status_code=204, headers=_NO_STORE_HEADERS)

    @app.get("/sentry-debug", response_class=JSONResponse)
    async def trigger_error():
        """Send a controlled test error to Sentry."""
        import sentry_sdk

        event_id = None
        try:
            _ = 1 / 0
        except ZeroDivisionError as exc:
            event_id = sentry_sdk.capture_exception(exc)

        return JSONResponse(
            status_code=500,
            content={
                "error": "Intentional Sentry test error",
                "event_id": str(event_id) if event_id else None,
            },
        )


def register_health_routes(app: FastAPI) -> None:
    """Register health, homelab and observability diagnostic routes."""
    _register_homelab_catalog_routes(app)
    _register_homelab_health_routes(app)
    _register_probe_routes(app)
    _register_health_board_routes(app)
