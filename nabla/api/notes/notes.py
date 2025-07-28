from datetime import datetime as dt
from typing import List

from fastapi import APIRouter, HTTPException, Path

from nabla.api.notes import crud
from nabla.api.notes.models import NoteDB, NoteSchema

router = APIRouter()


@router.post("/", response_model=NoteDB, status_code=201)
async def create_note(payload: NoteSchema):
    note_id = await crud.post(payload)
    created_date = dt.now().strftime("%Y-%m-%d %H:%M")

    response_object = {
        "id": note_id,
        "title": payload.title,
        "description": payload.description,
        "completed": payload.completed,
        "created_date": created_date,
    }
    return response_object


@router.get("/{id}/", response_model=NoteDB)
async def read_note(
    note_id: int = Path(..., gt=0),
):
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.get("/", response_model=List[NoteDB])
async def read_all_notes():
    return await crud.get_all()


@router.put("/{id}/", response_model=NoteDB)
async def update_note(
    payload: NoteSchema,
    note_id: int = Path(..., gt=0),
):  # Ensures the input is greater than 0
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    note_id = await crud.put(id, payload)  # type: ignore
    response_object = {
        "id": note_id,
        "title": payload.title,
        "description": payload.description,
        "completed": payload.completed,
    }
    return response_object


# DELETE route
@router.delete("/{id}/", response_model=NoteDB)
async def delete_note(note_id: int = Path(..., gt=0)):
    note = await crud.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await crud.delete(note_id)

    return note
