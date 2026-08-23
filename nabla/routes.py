"""Application route registration and handlers."""
import html
import os

import pyroscope
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, ORJSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import select
from starlette.routing import Mount

from nabla.api.db.database import SessionLocal
from nabla.api.health_board import prioritize_optional_truenas
from nabla.api.notes.models import Note
from nabla.utils.logger import logger


templates = Jinja2Templates(directory="templates")
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


def _move_root_mounts_last(app: FastAPI) -> None:
    """Keep catch-all root mounts behind concrete FastAPI routes.

    Starlette evaluates routes in registration order. A ``Mount('/')`` added
    before concrete routes captures requests such as ``/api`` and ``/metrics``.
    """
    root_mounts = [
        route
        for route in app.routes
        if isinstance(route, Mount) and getattr(route, "path", None) in ("", "/")
    ]
    for route in root_mounts:
        app.routes.remove(route)
        app.routes.append(route)


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""

    @app.get("/", response_class=HTMLResponse)
    @limiter.limit("100/second")
    def dashboard(request: Request):
        session = SessionLocal()
        notes = session.exec(select(Note)).all()
        return templates.TemplateResponse(
            "index.html", {"request": request, "notes": notes}
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return RedirectResponse("/vercel.svg", status_code=307)

    @app.get("/api/data")
    def get_sample_data():
        return {
            "data": [
                {"id": 1, "name": "Sample Item 1", "value": 100},
                {"id": 2, "name": "Sample Item 2", "value": 200},
                {"id": 3, "name": "Sample Item 3", "value": 300},
            ],
            "total": 3,
            "timestamp": "2024-01-01T00:00:00Z",
        }

    @app.get("/api/items/{item_id}")
    def get_item(item_id: int):
        return {
            "item": {
                "id": item_id,
                "name": f"Sample Item {item_id}",
                "value": item_id * 100,
            },
            "timestamp": "2024-01-01T00:00:00Z",
        }

    @app.get("/api", response_class=HTMLResponse)
    def read_root(request: Request):
        from nabla.api.ui import render_api_root_page

        page = render_api_root_page(
            title_suffix=os.getenv("TITLE_SUFFIX"),
            app_version=html.escape(str(request.app.version)),
        )
        return prioritize_optional_truenas(page)

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
        "/api/homelab/health",
        response_class=ORJSONResponse,
        tags=["Homelab", "Health"],
        summary="Public homelab endpoint health",
    )
    async def get_homelab_health():
        """Return a cached health snapshot for explicitly public homelab URLs."""
        from nabla.api.homelab_health import build_homelab_health_payload

        return await build_homelab_health_payload()

    @app.get(
        "/healthz",
        response_class=ORJSONResponse,
        tags=["Health"],
        summary="Deep healthcheck",
    )
    async def get_healthz(request: Request):
        """Return JSON: GET /health payload merged with Redis, Postgres, etc."""
        from nabla.api.db.database import engine
        from nabla.api.demo.socket.redis import redis
        from nabla.api.health_checks import build_healthz_payload

        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_healthz_payload(
                request, redis_client=redis, engine=engine
            )

    @app.get(
        "/sickz",
        response_class=ORJSONResponse,
        tags=["Health"],
        summary="Inverse reachability",
    )
    async def get_sickz(request: Request):
        """Return JSON: URL groups must not be reachable."""
        from nabla.api.health_checks import build_sickz_payload

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

    @app.exception_handler(Exception)
    def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        from datetime import datetime

        logger.opt(exception=exc).error("Unhandled exception on {}", request.url)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "timestamp": datetime.now().isoformat(),
            },
        )

    @app.get("/metrics")
    def prometheus_metrics():
        from prometheus_client import REGISTRY
        from prometheus_client.openmetrics.exposition import (
            CONTENT_TYPE_LATEST,
            generate_latest,
        )
        from starlette.responses import Response

        if os.environ.get("ENV") == "dev":
            return Response(generate_latest(REGISTRY), media_type="text/plain")
        return Response(
            generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    _move_root_mounts_last(app)
