from datetime import datetime
from typing import Any, cast

from databases.interfaces import Record

from nabla.api.db.database import SessionLocal, database
from nabla.api.notes.models import Note, NoteResponse, notes


# TODO session: Session = Depends(get_session)
async def post(payload: NoteResponse) -> int:
    """Persist a note and return its generated primary key."""
    session = SessionLocal()
    try:
        note = Note(
            title=payload.title,
            description=payload.description,
            type=payload.type,
            prompt=payload.prompt,
            completed=payload.completed,
            created_date=datetime.now(),
        )
        session.add(note)
        session.commit()
        session.refresh(note)
        return cast(int, note.id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # query = notes.insert().values(
    #     title=payload.title,
    #     description=payload.description,
    #     completed=payload.completed,
    #     created_date=created_date,
    # )
    # return await database.execute(query=query)


async def get(note_id: int) -> Record | None:
    query = notes.select().where(notes.c.id == note_id)
    return await database.fetch_one(query=query)


async def get_all() -> list[Record]:
    query = notes.select()
    return await database.fetch_all(query=query)


async def put(note_id: int, payload: NoteResponse) -> Any:
    created_date = datetime.now()
    query = (
        notes.update()
        .where(notes.c.id == note_id)
        .values(
            title=payload.title,
            description=payload.description,
            type=payload.type,
            prompt=payload.prompt,
            completed=payload.completed,
            created_date=created_date,
        )
        .returning(notes.c.id)
    )
    return await database.execute(query=query)


async def delete(note_id: int) -> Any:
    query = notes.delete().where(notes.c.id == note_id)
    return await database.execute(query=query)
