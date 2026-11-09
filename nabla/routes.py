"""Application route registration and handlers."""

import html
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from starlette.routing import Mount

from nabla.api.health_routes import register_health_routes
from nabla.api.owner_ui_session import (
    owner_ui_authenticated,
    register_owner_ui_session_routes,
)
from nabla.api.runtime_environment import runtime_mode
from nabla.api.topology_telemetry import fetch_topology_telemetry
from nabla.api.topology_ui import render_topology_page
from nabla.api.ui import render_api_root_page
from nabla.config_settings import get_settings
from nabla.rate_limit import limiter
from nabla.utils.logger import logger


templates = Jinja2Templates(directory="templates")
_API_ASSETS_DIR = Path(__file__).resolve().parent / "api" / "assets"


def _no_store(response: Response) -> None:
    """Assets must reflect the currently deployed application release."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"


def _register_api_assets(app: FastAPI) -> None:
    """Serve UI assets as a FastAPI frontend: routes win, no SPA fallback."""
    assets = APIRouter(dependencies=[Depends(_no_store)])
    assets.frontend("/api/assets", directory=_API_ASSETS_DIR, fallback=None)
    app.include_router(assets)


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

    @app.get("/api/topology-telemetry", include_in_schema=False)
    async def topology_telemetry(request: Request) -> JSONResponse:
        # Container names and infrastructure resource usage are OWNER-only.
        # Client-side visibility is not an authorization boundary.
        if not owner_ui_authenticated(request, get_settings()):
            return JSONResponse(
                {"detail": "Owner session required"},
                status_code=403,
                headers={"Cache-Control": "private, no-store"},
            )
        return JSONResponse(
            await fetch_topology_telemetry(),
            headers={"Cache-Control": "private, no-store"},
        )


def _register_operations_history(app: FastAPI) -> None:
    """Owner-authenticated, fixed-window Prometheus trend projection."""

    @app.get("/api/home/metrics/history", include_in_schema=False)
    async def operations_history(
        request: Request,
        window: str = "1h",
    ) -> JSONResponse:
        if not owner_ui_authenticated(request, get_settings()):
            return JSONResponse(
                {"detail": "Owner session required"},
                status_code=403,
                headers={"Cache-Control": "private, no-store"},
            )
        if window not in {"1h", "24h", "7d"} or any(key != "window" for key in request.query_params):
            return JSONResponse(
                {"detail": "Unsupported window"},
                status_code=422,
                headers={"Cache-Control": "private, no-store"},
            )
        from nabla.api.home_metrics_history import (  # noqa: PLC0415 - lazy OWNER-only import
            fetch_home_metrics_history,
        )

        return JSONResponse(
            await fetch_home_metrics_history(window),
            headers={
                "Cache-Control": "private, no-store",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )


def _register_runtime_resource_observer(app: FastAPI) -> None:
    """OWNER-only process sample, no continuous psutil polling."""

    @app.get("/api/runtime/resources", include_in_schema=False)
    async def runtime_resources(request: Request) -> JSONResponse:
        if not owner_ui_authenticated(request, get_settings()):
            return JSONResponse(
                {"detail": "Owner session required"},
                status_code=403,
                headers={"Cache-Control": "private, no-store"},
            )
        from nabla.api.runtime_cost_observer import snapshot_process_resources

        return JSONResponse(
            snapshot_process_resources(),
            headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"},
        )


def _register_operations_dashboard(app: FastAPI, *, database: bool) -> None:
    """Serve the light operations shell without fetching PostgreSQL or probes.

    Browser telemetry is loaded from existing public/OWNER endpoints only.
    The sensor demonstration remains available at /demo/sensors.
    """

    @app.get("/", response_class=HTMLResponse, operation_id="root_dashboard")
    @limiter.limit("100/second")
    def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"database_enabled": database, "runtime_mode": runtime_mode(request.url.hostname)},
            headers={
                "Cache-Control": "private, no-store, max-age=0",
                "Pragma": "no-cache",
                "X-Robots-Tag": "noindex, nofollow",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    "default-src 'none'; script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                    "img-src 'self'; font-src 'self'; "
                    "base-uri 'none'; form-action 'none'; "
                    "frame-ancestors 'none'; object-src 'none'"
                ),
            },
        )


def register_routes(app: FastAPI, *, database: bool = True) -> None:
    """Register all application routes; DB-backed pages require ``database``."""
    _register_api_assets(app)

    _register_operations_dashboard(app, database=database)

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
    _register_operations_history(app)
    _register_runtime_resource_observer(app)

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
    register_owner_ui_session_routes(app)

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
