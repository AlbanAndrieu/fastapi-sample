import json

# from datetime import datetime as dt
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field
from pytz import timezone as tz

# With PostgreSQL
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

from nabla.api.db.database import SessionLocal, engine
from nabla.api.demo.socket.redis import (
    REDIS_CHANNEL,
    REDIS_NOTES_CHANNEL,
    REDIS_TASK_QUEUE,
    redis,
)

Base = declarative_base()

# Use a PIN to specify metadata related to this engine
# Pin.override(engine, service="fastapisample")

# metadata = MetaData()
# notes = Table(
#     "notes",
#     metadata,
#     Column("id", Integer, primary_key=True),
#     Column("title", String(50)),
#     Column("description", String(50)),
#     Column("completed", String(8), default="False"),
#     Column(
#         "created_date",
#         String(50),
#         default=dt.now(tz("Europe/Paris")).strftime("%Y-%m-%d %H:%M"),
#     ),
# )


async def init_db():
    # SQLModel.metadata.create_all(engine)
    Base.metadata.create_all(engine)


# Reading note model with sqlalchemy
class Note(Base):
    __tablename__ = "note"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(50), nullable=False)
    description = Column(String(50), nullable=False)
    type = Column(String(10), default="note", nullable=False)
    prompt = Column(String(100), nullable=False)
    completed = Column(String(8), default="False", nullable=False)
    created_date = Column(DateTime, nullable=False)

    def __str__(self):
        return f"Note ID : {self.id}\tTitle : {self.title}\tDescription : {self.description}\tType : {self.type}\tPrompt : {self.prompt}\tCompleted : {self.completed}\tCreated Date : {self.created_date}"


# Response note model with pydantic validation
# class NoteResponse(SQLModel):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     title: str = Field(
#         ...,
#         min_length=3,
#         max_length=50,
#     )  # additional validation for the inputs
#     description: str = Field(..., min_length=3, max_length=50)
#     type: str = Field(default="note", min_length=3, max_length=10)
#     prompt: str = Field(..., min_length=3, max_length=100)
#     completed: bool = False
#     created_date: str = datetime.now(tz("Europe/Paris")).strftime("%Y-%m-%d %H:%M")


# Response note model with pydantic validation
class NoteResponse(BaseModel):
    title: str = Field(
        ...,
        min_length=3,
        max_length=50,
    )  # additional validation for the inputs
    description: str = Field(..., min_length=3, max_length=50)
    # type: str = Field(default="note", min_length=3, max_length=10)
    type: str
    prompt: str = Field(..., min_length=3, max_length=100)
    completed: bool = False
    created_date: str = Field(
        default_factory=lambda: datetime.now(tz("Europe/Paris")).strftime(
            "%Y-%m-%d %H:%M",
        ),
    )


class NoteData(NoteResponse):
    id: int

    def save_reading(self, data: Dict[str, Any]) -> None:
        """Save notes to PostgreSQL database"""
        session = SessionLocal()
        try:
            # Convert ISO string back to datetime object
            # timestamp = datetime.fromisoformat(data["timestamp"])
            created_date: str = datetime.now(tz("Europe/Paris")).strftime(
                "%Y-%m-%d %H:%M",
            )

            db_reading = Note(
                title=data["title"],
                description=data["description"],
                type=data["type"],
                prompt=data["prompt"],
                completed=data["completed"],
                created_date=created_date,
            )
            session.add(db_reading)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


async def enqueue_note(note_id, note_type, prompt):
    # note_id = str(uuid4())
    note = {"id": note_id, "type": note_type, "prompt": prompt}
    await redis.rpush(
        REDIS_CHANNEL + REDIS_TASK_QUEUE + REDIS_NOTES_CHANNEL,
        json.dumps(note),
    )
    return note_id


notes = Note.__table__
