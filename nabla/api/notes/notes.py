import typing
from datetime import datetime as dt
from typing import List

from databases.interfaces import Record
from fastapi import APIRouter, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastmcp import FastMCP
from redis.exceptions import RedisError

# from fastapi_cache.decorator import cache
from nabla.api.notes import crud
from nabla.api.notes.models import NoteData, NoteResponse, enqueue_note
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


@router.get("/notes/", response_model=List[NoteData])
async def get_notes(request: Request):
    API_REQUEST_COUNTER.labels(method="GET", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes").observe(0.1)

    notes = await read_all_notes()
    return templates.TemplateResponse(
        request,
        "_notes_list.html",
        {"notes": notes},
    )


async def read_all_notes():
    return await crud.get_all()


@router.post("/notes/add", response_class=HTMLResponse)
async def add_note(request: Request, title: str):
    note = NoteResponse(
        title=title,
        description="test description",
        type="note",
        prompt="test prompt",
        completed=False,
    )
    await crud.post(note)
    notes = await crud.get_all()
    return templates.TemplateResponse(
        request,
        "_notes_list.html",
        {"notes": notes},
    )


# @mcp.resource("notes://create")
@router.post("/notes/", status_code=201, response_model=NoteData)
async def create_note(payload: NoteResponse):
    API_REQUEST_COUNTER.labels(method="POST", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="POST", endpoint="/notes").observe(0.1)

    note_id = await crud.post(payload)
    created_date = dt.now().strftime("%Y-%m-%d %H:%M")

    response_object = {
        "id": note_id,
        "title": payload.title,
        "type": payload.type,
        "prompt": payload.prompt,
        "description": payload.description,
        "completed": payload.completed,
        "created_date": created_date,
    }
    return response_object


async def get_note_or_404(note_id: int) -> typing.Optional[Record]:
    note: typing.Optional[Record] = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


# @mcp.resource("notes://{note_id}/update")
@router.put("/notes/{note_id}/", response_model=NoteData)
async def update_note(
    payload: NoteResponse,
    note_id: int = Path(..., gt=0),
):  # Ensures the input is greater than 0
    existing_note = await get_note_or_404(note_id)
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
    created_date = existing_note["created_date"]
    if isinstance(created_date, dt):
        created_date = created_date.strftime("%Y-%m-%d %H:%M")
    response_object = {
        "id": updated_note_id,
        "title": payload.title,
        "type": payload.type,
        "prompt": payload.prompt,
        "description": payload.description,
        "completed": payload.completed,
        "created_date": created_date,
    }
    return response_object


@router.post("/notes/{note_id}", response_class=HTMLResponse)
async def update_note_form(
    request: Request,
    note_id: int,
    title: str = Form(...),
    content: str = Form(...),
):
    note = await get_note_or_404(note_id)
    note.title = title
    note.content = content
    return templates.TemplateResponse(request, "_note_item.html", {"note": note})


# @cache(expire=300)  # Cache for 5 minutes to avoid repeated execution of complex SQL
# @mcp.resource("notes://{note_id}/read")
# TODO  response_model=NoteData
@router.get("/notes/{note_id}/")
async def get_note_by_id(note_id: int):
    API_REQUEST_COUNTER.labels(
        method="GET",
        endpoint="/notes/{note_id}",
        http_status=200,
    ).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes/{note_id}").observe(0.1)
    return await read_note(note_id)


async def read_note(
    note_id: int = Path(..., gt=0),
):
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


# TODO  response_model=NoteData
@router.delete("/notes/{note_id}/")
async def delete_note(note_id: int = Path(..., gt=0)):
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await crud.delete(note_id)

    return note


@router.get("/notes/{note_id}/edit", response_class=HTMLResponse)
async def edit_note_form(request: Request, note_id: int):
    note = await get_note_or_404(note_id)
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
