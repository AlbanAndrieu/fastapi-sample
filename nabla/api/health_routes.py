"""Health and homelab route registration.

Keep dependency probes and diagnostic endpoints isolated from the general application
route module. The public paths and response contracts intentionally remain unchanged.
"""

from __future__ import annotations

import asyncio

import pyroscope
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, ORJSONResponse


async def _build_extended_healthz(request: Request) -> dict:
    """Compose deep health with optional platform and observability checks."""
    from nabla.api.db.database import engine
    from nabla.api.demo.socket.redis import redis
    from nabla.api.health_checks import build_healthz_payload
    from nabla.api.observability_health import enrich_optional_observability_checks
    from nabla.api.platform_health import enrich_optional_platform_checks

    payload = await build_healthz_payload(request, redis_client=redis, engine=engine)
    payload = await enrich_optional_platform_checks(payload)
    return await enrich_optional_observability_checks(payload)


def register_health_routes(app: FastAPI) -> None:
    """Register health, homelab and observability diagnostic routes."""

    @app.get(
        "/api/homelab-services",
        response_class=ORJSONResponse,
        tags=["Homelab"],
        summary="Homelab service catalog",
    )
    async def get_homelab_services():
        """Expose the validated homelab catalog through FastAPI."""
        from nabla.api.homelab_catalog import fetch_homelab_catalog

        catalog = await fetch_homelab_catalog()
        return catalog.model_dump(mode="json", by_alias=True, exclude_none=True)

    @app.get(
        "/api/homelab-topology",
        response_class=ORJSONResponse,
        tags=["Homelab"],
        summary="Declared homelab service topology",
    )
    async def get_homelab_topology():
        """Expose the validated design-time topology sourced from nabla-compose."""
        from nabla.api.homelab_topology import fetch_homelab_topology

        topology = await fetch_homelab_topology()
        return topology.model_dump(mode="json", by_alias=True, exclude_none=True)

    @app.get(
        "/api/homelab/health",
        response_class=ORJSONResponse,
        tags=["Homelab", "Health"],
        summary="Homelab and platform health",
    )
    async def get_homelab_health():
        """Return detailed homelab services plus shared core/platform components."""
        from nabla.api.component_health import build_component_checks, component_status
        from nabla.api.db.database import engine
        from nabla.api.demo.socket.redis import redis
        from nabla.api.homelab_health import build_homelab_health_payload

        homelab_task = asyncio.create_task(build_homelab_health_payload())
        components = await build_component_checks(
            redis_client=redis,
            engine=engine,
            homelab_snapshot=homelab_task,
        )
        homelab_payload = await homelab_task
        homelab_payload["components_status"] = component_status(components)
        homelab_payload["components"] = components
        return homelab_payload

    @app.get(
        "/healthz",
        response_class=ORJSONResponse,
        tags=["Health"],
        summary="Deep healthcheck",
    )
    async def get_healthz(request: Request):
        """Return runtime health plus deep dependency and service probes."""
        with pyroscope.tag_wrapper({"function": "fast"}):
            return await _build_extended_healthz(request)

    @app.get(
        "/sickz",
        response_class=ORJSONResponse,
        tags=["Health"],
        summary="Inverse reachability",
    )
    async def get_sickz(request: Request):
        """Return JSON: URL groups must not be reachable."""
        from nabla.api.sickz_checks import build_sickz_payload

        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_sickz_payload(request)

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
