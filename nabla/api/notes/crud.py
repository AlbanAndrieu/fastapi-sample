import typing
from datetime import datetime as dt

from databases.interfaces import Record

from nabla.api.db.database import database
from nabla.api.notes.models import NoteResponse, notes


async def post(payload: NoteResponse) -> int:
    """Insert a note asynchronously and return its persisted identifier."""
    query = (
        notes.insert()
        .values(
            title=payload.title,
            description=payload.description,
            type=payload.type,
            prompt=payload.prompt,
            completed=payload.completed,
            created_date=dt.now(),
        )
        .returning(notes.c.id)
    )
    return await database.execute(query=query)


async def get(note_id: int) -> typing.Optional[Record]:
    query = notes.select().where(notes.c.id == note_id)
    return await database.fetch_one(query=query)


async def get_all() -> typing.List[Record]:
    query = notes.select()
    return await database.fetch_all(query=query)


async def put(note_id: int, payload: NoteResponse) -> typing.Any:
    """Update note content without replacing its original creation timestamp."""
    query = (
        notes.update()
        .where(notes.c.id == note_id)
        .values(
            title=payload.title,
            description=payload.description,
            type=payload.type,
            prompt=payload.prompt,
            completed=payload.completed,
        )
        .returning(notes.c.id)
    )
    return await database.execute(query=query)


async def delete(note_id: int) -> typing.Any:
    query = notes.delete().where(notes.c.id == note_id)
    return await database.execute(query=query)
