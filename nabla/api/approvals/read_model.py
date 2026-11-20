"""Owner-only, read-only inventory of pending hardware approval challenges.

PostgreSQL is authoritative; neither Redis nor Notes fields authorize applies.
No mutation endpoint is registered here.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nabla.api.approvals.persistence import pending_list
from nabla.api.db.database import database
from nabla.api.owner_ui_session import owner_ui_authenticated
from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.config_settings import get_settings

_HEADERS = {"Cache-Control": "private, no-store, max-age=0", "X-Robots-Tag": "noindex, nofollow"}


def _enabled(settings: object) -> bool:
    return (homelab_runtime_detected()
            and getattr(settings, "operation_approval_read_model_enabled", False) is True)


def register_approval_read_routes(app: FastAPI) -> None:
    @app.get("/api/homelab/approvals/pending", include_in_schema=False)
    async def pending(request: Request) -> JSONResponse:
        settings = get_settings()
        if not _enabled(settings):
            return JSONResponse({"detail": "Not found"}, status_code=404, headers=_HEADERS)
        if not owner_ui_authenticated(request, settings):
            return JSONResponse({"detail": "Owner session required"}, status_code=403, headers=_HEADERS)
        if request.query_params:
            return JSONResponse({"detail": "Parameters not accepted"}, status_code=422, headers=_HEADERS)
        if not database.is_connected:
            return JSONResponse({"state": "database_unavailable"}, status_code=503, headers=_HEADERS)
        try:
            async with asyncio.timeout(2):
                records = await database.fetch_all(pending_list(limit=25))
            rows = []
            for record in records:
                data = dict(getattr(record, "_mapping", record))
                expires = data.get("expires_at")
                if not isinstance(expires, datetime):
                    raise ValueError("Invalid approval row")
                rows.append({
                    "challengeSha256": data["challenge_sha256"],
                    "repository": data["repository"],
                    "workflow": data["workflow"],
                    "runId": data["run_id"],
                    "expiresAt": expires.astimezone(timezone.utc).isoformat(),
                    "status": "pending",
                })
        except (Exception, TimeoutError):
            # Never leak DB errors, plan, signature, credentials or SQL.
            return JSONResponse({"state": "database_unavailable"}, status_code=503, headers=_HEADERS)
        return JSONResponse(
            {"state": "pending" if rows else "empty", "count": len(rows), "approvals": rows},
            headers=_HEADERS,
        )
