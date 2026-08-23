"""Application route registration and handlers."""
import html
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import select
from starlette.routing import Mount

from nabla.api.db.database import SessionLocal
from nabla.api.health_board import prioritize_optional_truenas
from nabla.api.health_routes import register_health_routes
from nabla.api.notes.models import Note
from nabla.utils.logger import logger


templates = Jinja2Templates(directory="templates")
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


def _move_root_mounts_last(app: FastAPI) -> None:
    """Keep catch-all root mounts behind concrete FastAPI routes."""
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

    register_health_routes(app)

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
