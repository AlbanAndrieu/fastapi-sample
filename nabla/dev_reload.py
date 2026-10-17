"""Development-only browser reload stream built on FastAPI Server-Sent Events."""

from __future__ import annotations

from collections.abc import AsyncIterable
from pathlib import Path
import uuid

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from watchfiles import awatch

_ROOT = Path(__file__).resolve().parent.parent
WATCHED_PATHS = (_ROOT / "templates", _ROOT / "nabla" / "api" / "assets", _ROOT / "nabla" / "data")

# A new process (``fastapi dev`` restart after a Python edit) gets a new id;
# the browser reloads when the id it reconnects to differs from the first one.
BOOT_ID = uuid.uuid4().hex

router = APIRouter(include_in_schema=False)


@router.get("/hot-reload", response_class=EventSourceResponse)
async def hot_reload() -> AsyncIterable[ServerSentEvent]:
    """Announce the server boot id, then emit ``reload`` on watched file changes."""
    yield ServerSentEvent(data=BOOT_ID, event="boot")
    paths = [path for path in WATCHED_PATHS if path.is_dir()]
    if not paths:
        return
    async for _changes in awatch(*paths):
        yield ServerSentEvent(data=BOOT_ID, event="reload")
