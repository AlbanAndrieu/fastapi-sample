"""Application route registration and handlers."""

import html
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from sqlmodel import select
from starlette.routing import Mount

from nabla.api.db.database import SessionLocal
from nabla.api.health_routes import register_health_routes
from nabla.api.notes.models import Note
from nabla.api.runtime_environment import runtime_mode
from nabla.api.topology_ui import render_topology_page
from nabla.api.ui import render_api_root_page
from nabla.rate_limit import limiter
from nabla.utils.logger import logger


templates = Jinja2Templates(directory="templates")
_API_ASSETS_DIR = Path(__file__).resolve().parent / "api" / "assets"


class NoStoreStaticFiles(StaticFiles):
    """Static assets that must reflect the currently deployed application release."""

    async def get_response(self, path: str, scope: dict) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response


def _move_root_mounts_last(app: FastAPI) -> None:
    """Keep catch-all root mounts behind concrete FastAPI routes."""
    root_mounts = [route for route in app.routes if isinstance(route, Mount) and getattr(route, "path", None) in ("", "/")]
    for route in root_mounts:
        app.routes.remove(route)
        app.routes.append(route)


def _register_topology_dashboard(app: FastAPI) -> None:
    """Register the standalone declared-topology visualization screen."""

    @app.get("/api/topology", response_class=HTMLResponse, include_in_schema=False)
    async def topology_dashboard(request: Request) -> HTMLResponse:
        return HTMLResponse(
            render_topology_page(
                title_suffix=os.getenv("TITLE_SUFFIX"),
                app_version=html.escape(str(request.app.version)),
            ),
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
            },
        )


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""
    app.mount(
        "/api/assets",
        NoStoreStaticFiles(directory=_API_ASSETS_DIR),
        name="api-assets",
    )

    @app.get("/", response_class=HTMLResponse, operation_id="root_dashboard")
    @limiter.limit("100/second")
    def dashboard(request: Request):
        session = SessionLocal()
        notes = session.exec(select(Note)).all()
        return templates.TemplateResponse("index.html", {"request": request, "notes": notes})

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
    async def read_root(request: Request) -> HTMLResponse:
        return HTMLResponse(
            render_api_root_page(
                title_suffix=os.getenv("TITLE_SUFFIX"),
                app_version=html.escape(str(request.app.version)),
                runtime_mode=runtime_mode(request.url.hostname),
            ),
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
            },
        )

    _register_topology_dashboard(app)

    @app.get("/api/runtime-version", include_in_schema=False)
    async def api_runtime_version(request: Request) -> JSONResponse:
        """Expose only the deployed version/runtime mode for cross-runtime drift UI."""
        return JSONResponse(
            {
                "version": str(request.app.version),
                "runtime_mode": runtime_mode(request.url.hostname),
            },
            headers={
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )

    register_health_routes(app)

    @app.exception_handler(Exception)
    def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception on %s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "timestamp": datetime.now().isoformat(),
            },
        )

    @app.get("/metrics")
    def prometheus_metrics():
        if os.environ.get("ENV") == "dev":
            return Response(generate_latest(REGISTRY), media_type="text/plain")
        return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})

    _move_root_mounts_last(app)
