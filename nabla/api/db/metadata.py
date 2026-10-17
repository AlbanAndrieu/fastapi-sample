"""Aggregate ORM metadata for Alembic and schema comparisons.

Kept apart from ``nabla.api.db.database`` because the model modules import
that module; importing them here creates no cycle.
"""

from sqlalchemy import MetaData

from nabla.api.demo.models import Base as DemoBase
from nabla.api.notes.models import Base as NoteBase
from nabla.api.users.models import Base as UserBase


def application_metadata() -> list[MetaData]:
    """Return every ORM ``MetaData`` whose tables the application persists.

    ``alembic/env.py`` targets this list so autogenerate and schema comparisons
    see ``user``, ``note`` and ``sensor_reading`` together.
    """
    return [UserBase.metadata, NoteBase.metadata, DemoBase.metadata]
