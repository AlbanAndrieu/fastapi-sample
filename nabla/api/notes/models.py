# from datetime import datetime as dt
from datetime import datetime
from typing import Any, Dict, Final

from ddtrace import patch
from pydantic import BaseModel, Field
from pytz import timezone as tz

# With PostgreSQL
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from nabla.config_settings import get_settings

# rom databases import Database


Base = declarative_base()

# Database url if none is passed the default one is used
DB_URL: Final[str] = str(get_settings().db_url)

patch(sqlalchemy=True)

# SQLAlchemy
engine = create_engine(DB_URL)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

# Create tables
Base.metadata.create_all(bind=engine)


# notes = Table("notes", Base.metadata, autoload_with=engine)
class NoteReading(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(50), nullable=False)
    description = Column(String(50), nullable=False)
    completed = Column(String(8), default="False", nullable=False)
    created_date = Column(DateTime, nullable=False)

    def __str__(self):
        return f"Note ID : {self.id}\tTitle : {self.title}\tDescription : {self.description}\tCompleted : {self.completed}\tCreated Date : {self.created_date}"


class NoteSchema(BaseModel):
    title: str = Field(
        ...,
        min_length=3,
        max_length=50,
    )  # additional validation for the inputs
    description: str = Field(..., min_length=3, max_length=50)
    completed: str = "False"
    created_date: str = datetime.now(tz("Europe/Paris")).strftime("%Y-%m-%d %H:%M")


class NoteDB(NoteSchema):
    id: int

    def save_reading(self, data: Dict[str, Any]) -> None:
        """Save notes to PostgreSQL database"""
        db = SessionLocal()
        try:
            # Convert ISO string back to datetime object
            # timestamp = datetime.fromisoformat(data["timestamp"])
            created_date: str = datetime.now(tz("Europe/Paris")).strftime(
                "%Y-%m-%d %H:%M",
            )

            db_reading = NoteReading(
                title=data["title"],
                description=data["description"],
                completed=data["completed"],
                created_date=created_date,
            )
            db.add(db_reading)
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


notes = NoteReading.__table__
