from datetime import datetime as dt

from nabla.api.demo.models import SessionLocal
from nabla.api.notes.models import NoteReading, NoteSchema, notes
from nabla.db import database

# from nabla.db import database, notes
db = SessionLocal()


async def post(payload: NoteSchema):
    created_date = dt.now().strftime("%Y-%m-%d %H:%M")
    db.add(
        NoteReading(
            title=payload.title,
            description=payload.description,
            completed=payload.completed,
            created_date=created_date,
        ),
    )
    db.commit()
    db.close()
    return payload

    # query = notes.insert().values(
    #     title=payload.title,
    #     description=payload.description,
    #     completed=payload.completed,
    #     created_date=created_date,
    # )
    # return await database.execute(query=query)


async def get(note_id: int):
    query = notes.select().where(notes.c.id == note_id)
    return await database.fetch_one(query=query)


async def get_all():
    query = notes.select()
    return await database.fetch_all(query=query)


async def put(note_id: int, payload=NoteSchema):
    created_date = dt.now().strftime("%Y-%m-%d %H:%M")
    query = (
        notes.update()
        .where(notes.c.id == note_id)
        .values(
            title=payload.title,
            description=payload.description,
            completed=payload.completed,
            created_date=created_date,
        )
        .returning(notes.c.id)
    )
    return await database.execute(query=query)


async def delete(note_id: int):
    query = notes.delete().where(notes.c.id == note_id)
    return await database.execute(query=query)
