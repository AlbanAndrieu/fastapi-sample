"""Application route registration and handlers."""
import os
import html
from fastapi import Request, FastAPI
from fastapi.responses import ORJSONResponse, RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from nabla.api.db.database import SessionLocal
from nabla.api.notes.models import Note
from nabla.utils.logger import logger
from nabla.config_settings import APP_VERSION
import pyroscope
from slowapi import Limiter
from slowapi.util import get_remote_address


templates = Jinja2Templates(directory="templates")
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


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

        return render_api_root_page(
            title_suffix=os.getenv("TITLE_SUFFIX"),
            app_version=html.escape(str(request.app.version)),
        )

    @app.get("/healthz", response_class=ORJSONResponse, tags=["Health"], summary="Deep healthcheck")
    async def get_healthz(request: Request):
        """Return JSON: GET /health payload merged with Redis, Postgres, etc."""
        from nabla.api.health_checks import build_healthz_payload
        from nabla.api.db.database import engine
        from nabla.api.demo.socket.redis import redis

        with pyroscope.tag_wrapper({"function": "fast"}):
            return await build_healthz_payload(request, redis_client=redis, engine=engine)

    @app.get("/sickz", response_class=ORJSONResponse, tags=["Health"], summary="Inverse reachability")
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
            content={"error": "Internal server error", "timestamp": datetime.now().isoformat()},
        )

    @app.get("/metrics")
    def prometheus_metrics():
        from prometheus_client import REGISTRY
        from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest
        from starlette.responses import Response

        if os.environ.get("ENV") == "dev":
            return Response(generate_latest(REGISTRY), media_type="text/plain")
        return Response(
            generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )
