import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Annotated, Any, Dict

from pydantic import AfterValidator, BaseModel, Field

# With PostgreSQL
from sqlalchemy import Boolean, Column, DateTime, Integer, String, false
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
    # Boolean/timestamptz since migration 4b7c2d9e1a6f (legacy: VARCHAR(8)
    # "True"/"False" and naive TIMESTAMP).
    completed = Column(Boolean, default=False, server_default=false(), nullable=False)
    created_date = Column(DateTime(timezone=True), nullable=False)

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


def utc_now() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC.

    Naive values are legacy rows/payloads written before the timestamptz
    migration; they are interpreted as UTC, matching the migration's
    ``AT TIME ZONE 'UTC'`` conversion.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


# Request payload for note create/update. The historic name is kept because
# routes, tests and the MCP/OpenAPI schema reference it. ``completed`` accepts
# legacy string spellings ("True"/"False"/"true"/"1"...) through Pydantic's
# lax boolean parsing; it is always serialized as a JSON boolean.
class NoteResponse(BaseModel):
    title: str = Field(
        min_length=3,
        max_length=50,
    )  # additional validation for the inputs
    description: str = Field(min_length=3, max_length=50)
    # type: str = Field(default="note", min_length=3, max_length=10)
    type: str
    prompt: str = Field(min_length=3, max_length=100)
    completed: bool = False
    # Client-provided values are accepted for compatibility but the server
    # owns the persisted creation timestamp.
    created_date: UtcDatetime = Field(default_factory=utc_now)


class NoteData(NoteResponse):
    """Typed note representation returned by read/create/update/delete."""

    id: int

    @classmethod
    def from_record(cls, record: Any) -> "NoteData":
        """Build a response from a ``databases`` Record or a plain mapping."""
        mapping: Mapping[str, Any] = getattr(record, "_mapping", record)
        return cls.model_validate(dict(mapping))

    def save_reading(self, data: Dict[str, Any]) -> None:
        """Save notes to PostgreSQL database"""
        session = SessionLocal()
        try:
            created_date = utc_now()

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
