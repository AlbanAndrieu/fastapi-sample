# ruff: noqa: C901, PLC0415 -- route-local imports keep optional probes lazy.

"""Health and homelab route registration.

Keep dependency probes and diagnostic endpoints isolated from the general application
route module. The public paths and response contracts intentionally remain unchanged.
"""

from __future__ import annotations

from typing import Annotated, Any

import pyroscope
from fastapi import FastAPI, Query, Request, Response, status
from fastapi.responses import JSONResponse

from nabla.api.homelab_declared import DeclaredServiceCatalog
from nabla.api.homelab_models import HomelabCatalog
from nabla.api.homelab_runtime import TrueNASRuntimeSnapshot
from nabla.api.homelab_topology import HomelabTopology
from nabla.utils.logger import logger


_NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}


def register_health_routes(app: FastAPI) -> None:
    """Register health, homelab and observability diagnostic routes."""

    @app.get(
        "/api/homelab-services",
        response_model=HomelabCatalog,
        response_model_exclude_none=True,
        tags=["Homelab"],
        summary="FastAPI-owned homelab exposure catalog",
    )
    async def get_homelab_services():
        """Expose the FastAPI-owned presentation and exposure policy catalog."""
        from nabla.api.homelab_catalog import fetch_homelab_catalog

        return await fetch_homelab_catalog()

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
    async def get_readiness() -> JSONResponse:
        from nabla.api.db.database import engine
        from nabla.api.demo.socket.redis import redis
        from nabla.api.health_contracts import build_readiness_payload

        payload, ready = await build_readiness_payload(
            redis_client=redis,
            engine=engine,
            version=app.version,
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

        response.headers.update(_NO_STORE_HEADERS)
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_sickz_snapshot(request)

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
        return await get_health_board_snapshot(
            request,
            force_refresh=force_refresh,
        )

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
