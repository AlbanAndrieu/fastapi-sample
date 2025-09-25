from datetime import datetime as dt
from typing import List

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastmcp import FastMCP
from sqlmodel import select

from nabla.api.db.database import SessionLocal

# from fastapi_cache.decorator import cache
from nabla.api.notes import crud
from nabla.api.notes.models import NoteData, NoteResponse
from nabla.utils.prometheus import API_REQUEST_COUNTER, API_REQUEST_SUMMARY

router = APIRouter()
mcp = FastMCP(name="NotesServer")

templates = Jinja2Templates(directory="templates")


@mcp.prompt
def summarize_request(text: str) -> str:
    """Generate a prompt asking for a summary."""
    return f"Please summarize the following text:\n\n{text}"


@router.get("/notes/", response_model=List[NoteData])
async def get_notes():
    API_REQUEST_COUNTER.labels(method="GET", endpoint="/notes", http_status=200).inc()
    API_REQUEST_SUMMARY.labels(method="GET", endpoint="/notes").observe(0.1)
    return await read_all_notes()


async def read_all_notes():
    return await crud.get_all()


@router.post("/notes/add", response_class=HTMLResponse)
def add_note(request: Request, title: str):
    note = NoteResponse(title=title, description="test description", type="note", prompt="test prompt", completed=False)
    session = SessionLocal()
    session.add(note)
    session.commit()
    session.refresh(note)
    notes = session.exec(select(NoteResponse)).all()
    return templates.TemplateResponse(
        "notes.html",
        {"request": request, "notes": notes},
    )



# @mcp.resource("notes://create")
# TODO  response_model=NoteData
@router.post("/notes/", status_code=201)
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


# @mcp.resource("notes://{note_id}/update")
# TODO  response_model=NoteData
@router.put("/notes/{note_id}/")
async def update_note(
    payload: NoteResponse,
    note_id: int = Path(..., gt=0),
):  # Ensures the input is greater than 0
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    note_id = await crud.put(id, payload)  # type: ignore
    note_id = enqueue_note(note_id, payload.type, payload.prompt)
    response_object = {
        "id": note_id,
        "title": payload.title,
        "type": payload.type,
        "prompt": payload.prompt,
        "description": payload.description,
        "completed": payload.completed,
    }
    return response_object

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
