import typing
from typing import Annotated, List

from databases.interfaces import Record
from fastapi import APIRouter, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastmcp import FastMCP
from redis.exceptions import RedisError

# from fastapi_cache.decorator import cache
from nabla.api.notes import crud
from nabla.api.notes.models import NoteData, NoteResponse, enqueue_note, utc_now
from nabla.utils.logger import logger
from nabla.utils.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

router = APIRouter()
mcp = FastMCP(name="NotesServer")

# TODO from fastapi_crudrouter import SQLAlchemyCRUDRouter

# router = SQLAlchemyCRUDRouter(schema=ItemSchema, db_model=ItemModel, db=session)
# app.include_router(router)

templates = Jinja2Templates(directory="templates")


@mcp.prompt
def summarize_request(text: str) -> str:
    """Generate a prompt asking for a summary."""
    return f"Please summarize the following text:\n\n{text}"


NOTE_NOT_FOUND = "Note not found"
NOT_FOUND_RESPONSE: dict[int | str, dict[str, typing.Any]] = {
    404: {"description": NOTE_NOT_FOUND},
}


# The list endpoint renders an HTMX fragment; it never returned JSON, so it is
# documented as HTML instead of advertising a NoteData list it does not emit.
@router.get("/notes/", response_class=HTMLResponse)
async def get_notes(request: Request):
    API_REQUEST_COUNTER.labels(method="GET", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes").observe(0.1)

    notes = await read_all_notes()
    return templates.TemplateResponse(
        request,
        "_notes_list.html",
        {"notes": notes},
    )


async def read_all_notes() -> List[NoteData]:
    """Return normalized notes (boolean ``completed``, aware UTC timestamps)."""
    return [NoteData.from_record(record) for record in await crud.get_all()]


# HTMX form fields mirror the ``NoteResponse`` constraints so invalid input is
# rejected with 422 before reaching the CRUD layer.
NoteTitleForm = Annotated[str, Form(min_length=3, max_length=50)]
NoteDescriptionForm = Annotated[str, Form(min_length=3, max_length=50)]
NoteId = Annotated[int, Path(gt=0)]


def render_notes_list(request: Request, notes: List[NoteData]) -> HTMLResponse:
    """Render the ``#notes-list`` HTMX fragment."""
    return templates.TemplateResponse(request, "_notes_list.html", {"notes": notes})


def render_note_item(request: Request, note: NoteData) -> HTMLResponse:
    """Render one ``#note-{id}`` HTMX fragment."""
    return templates.TemplateResponse(request, "_note_item.html", {"note": note})


@router.post("/notes/add", response_class=HTMLResponse)
async def add_note(request: Request, title: NoteTitleForm):
    note = NoteResponse(
        title=title,
        description="test description",
        type="note",
        prompt="test prompt",
        completed=False,
    )
    await crud.post(note)
    return render_notes_list(request, await read_all_notes())


# @mcp.resource("notes://create")
@router.post("/notes/", status_code=201)
async def create_note(payload: NoteResponse) -> NoteData:
    API_REQUEST_COUNTER.labels(method="POST", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="POST", endpoint="/notes").observe(0.1)

    created_date = utc_now()
    note_id = await crud.post(payload, created_date=created_date)
    return NoteData(
        **payload.model_dump(exclude={"created_date"}),
        id=note_id,
        created_date=created_date,
    )


async def get_note_or_404(note_id: int) -> Record:
    note: typing.Optional[Record] = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail=NOTE_NOT_FOUND)
    return note


# @mcp.resource("notes://{note_id}/update")
@router.put("/notes/{note_id}/", responses=NOT_FOUND_RESPONSE)
async def update_note(
    payload: NoteResponse,
    note_id: Annotated[int, Path(gt=0)],
) -> NoteData:
    existing_note = NoteData.from_record(await get_note_or_404(note_id))
    updated_note_id = await crud.put(note_id, payload)
    try:
        await enqueue_note(updated_note_id, payload.type, payload.prompt)
    except (OSError, RedisError) as exc:
        logger.warning(
            "note_queue_unavailable",
            note_id=updated_note_id,
            exception_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Note saved but background processing is unavailable",
        ) from exc
    return NoteData(
        **payload.model_dump(exclude={"created_date"}),
        id=updated_note_id,
        created_date=existing_note.created_date,
    )


async def save_note_changes(existing_note: NoteData, **changes: typing.Any) -> NoteData:
    """Apply field changes through the typed CRUD, keeping ``created_date``.

    Database records are immutable; the normalized ``NoteData`` is merged with
    ``changes``, validated as ``NoteResponse`` and persisted with ``crud.put``.
    """
    payload = NoteResponse(
        **(existing_note.model_dump(exclude={"id", "created_date"}) | changes),
    )
    await crud.put(existing_note.id, payload)
    return NoteData(
        **payload.model_dump(exclude={"created_date"}),
        id=existing_note.id,
        created_date=existing_note.created_date,
    )


@router.post("/notes/{note_id}", response_class=HTMLResponse, responses=NOT_FOUND_RESPONSE)
async def update_note_form(
    request: Request,
    note_id: NoteId,
    title: NoteTitleForm,
    description: NoteDescriptionForm,
):
    existing_note = await read_note(note_id)
    note = await save_note_changes(existing_note, title=title, description=description)
    return render_note_item(request, note)


@router.post("/notes/{note_id}/toggle", response_class=HTMLResponse, responses=NOT_FOUND_RESPONSE)
async def toggle_note_form(request: Request, note_id: NoteId):
    existing_note = await read_note(note_id)
    note = await save_note_changes(existing_note, completed=not existing_note.completed)
    return render_note_item(request, note)


@router.post("/notes/{note_id}/delete", response_class=HTMLResponse, responses=NOT_FOUND_RESPONSE)
async def delete_note_form(request: Request, note_id: NoteId):
    await read_note(note_id)
    await crud.delete(note_id)
    return render_notes_list(request, await read_all_notes())


# @cache(expire=300)  # Cache for 5 minutes to avoid repeated execution of complex SQL
# @mcp.resource("notes://{note_id}/read")
@router.get("/notes/{note_id}/", responses=NOT_FOUND_RESPONSE)
async def get_note_by_id(note_id: int) -> NoteData:
    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/notes/{note_id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes/{note_id}").observe(0.1)
    return await read_note(note_id)


async def read_note(note_id: int) -> NoteData:
    return NoteData.from_record(await get_note_or_404(note_id))


# Notes have no owner column and the router has no authentication dependency,
# so there is no per-user authorization decision (no 403) to make here.
@router.delete("/notes/{note_id}/", responses=NOT_FOUND_RESPONSE)
async def delete_note(note_id: Annotated[int, Path(gt=0)]) -> NoteData:
    """Delete a note and return the deleted representation (backward compatible)."""
    note = await read_note(note_id)
    await crud.delete(note_id)
    return note


@router.get("/notes/{note_id}/edit", response_class=HTMLResponse, responses=NOT_FOUND_RESPONSE)
async def edit_note_form(request: Request, note_id: NoteId):
    note = await read_note(note_id)
    return templates.TemplateResponse(request, "_note_item_edit.html", {"note": note})


# @app.exception_handler(NotFoundInJM)
# async def not_found_jm_handler(request: Request, exc: NotFoundInJM):
#        status_code=404,
#        content={"message": str(exc)},
#    )
#
#
# @app.exception_handler(CrudError)
# async def crud_error_handler(request: Request, exc: CrudError):
#    logger.error("Error while querying the DB")
#    logger.exception(exc)
#    return JSONResponse(
#        status_code=500,
#        content={"message": f"Error while querying the DB: {exc}"},
#    )
#
#
# @app.exception_handler(Exception)
# async def exception_handler(request: Request, exc: Exception):
#    logger.error("Unexpected error")
#    logger.exception(exc)
#    return JSONResponse(
#        status_code=500,
#        content={"message": f"Unexpected error: {exc}"},
#    )
