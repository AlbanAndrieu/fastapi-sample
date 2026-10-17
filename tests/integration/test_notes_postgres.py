"""Real PostgreSQL coverage for the notes migration and CRUD roundtrip.

Run only against a disposable database, for example::

    docker run --rm -d --name notes-pg -e POSTGRES_PASSWORD=<pw> \
        -p 127.0.0.1:55432:5432 postgres:17-alpine
    NOTES_POSTGRES_INTEGRATION_URL=postgresql://postgres:<pw>@127.0.0.1:55432/postgres \
        uv run pytest tests/integration/test_notes_postgres.py -m integration

The tests drop and recreate the ``note`` table; never point them at a shared,
staging or production database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from databases import Database
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from nabla.api.notes import crud
from nabla.api.notes.models import NoteData, NoteResponse

_PG_URL = os.getenv("NOTES_POSTGRES_INTEGRATION_URL", "").strip()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _PG_URL,
        reason="NOTES_POSTGRES_INTEGRATION_URL is required for PostgreSQL notes tests",
    ),
]

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "4b7c2d9e1a6f_note_completed_boolean_utc_timestamp.py"
_LEGACY_ROWS = [
    ("first", "True", datetime(2026, 10, 17, 8, 30)),
    ("second", "False", datetime(2026, 1, 2, 3, 4, 5)),
    ("third", "true", datetime(2025, 12, 31, 23, 59)),
]


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("notes_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sync_url() -> str:
    return (
        make_url(_PG_URL)
        .set(drivername="postgresql+psycopg")
        .render_as_string(
            hide_password=False,
        )
    )


def _async_url() -> str:
    return (
        make_url(_PG_URL)
        .set(drivername="postgresql+asyncpg")
        .render_as_string(
            hide_password=False,
        )
    )


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = sa.create_engine(_sync_url())
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP TABLE IF EXISTS note"))
        engine.dispose()


def _create_legacy_table(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS note"))
        connection.execute(
            sa.text(
                "CREATE TABLE note ("
                "id SERIAL PRIMARY KEY, title VARCHAR(50) NOT NULL, "
                "description VARCHAR(50) NOT NULL, "
                "type VARCHAR(10) NOT NULL DEFAULT 'note', "
                "prompt VARCHAR(100) NOT NULL, "
                "completed VARCHAR(8) NOT NULL, "
                "created_date TIMESTAMP WITHOUT TIME ZONE NOT NULL)",
            ),
        )
        for title, completed, created in _LEGACY_ROWS:
            connection.execute(
                sa.text(
                    "INSERT INTO note (title, description, prompt, completed, created_date) VALUES (:t, 'desc', 'prompt', :c, :d)",
                ),
                {"t": title, "c": completed, "d": created},
            )


def _run(engine: sa.Engine, step: str) -> None:
    migration = _load_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(migration, step)()


def _column_types(engine: sa.Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'note'",
            ),
        )
        return {str(name): str(data_type) for name, data_type in rows}


def _rows(engine: sa.Engine) -> list[tuple[str, object, datetime]]:
    with engine.connect() as connection:
        result = connection.execute(
            sa.text("SELECT title, completed, created_date FROM note ORDER BY id"),
        )
        return [(row[0], row[1], row[2]) for row in result]


def test_migration_upgrade_and_downgrade_roundtrip(engine: sa.Engine) -> None:
    _create_legacy_table(engine)

    _run(engine, "upgrade")

    types = _column_types(engine)
    assert types["completed"] == "boolean"
    assert types["created_date"] == "timestamp with time zone"
    assert _rows(engine) == [
        ("first", True, datetime(2026, 10, 17, 8, 30, tzinfo=timezone.utc)),
        ("second", False, datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        ("third", True, datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)),
    ]

    # Idempotent on an already-converted schema (e.g. created by create_all).
    _run(engine, "upgrade")
    assert _column_types(engine) == types

    _run(engine, "downgrade")

    legacy_types = _column_types(engine)
    assert legacy_types["completed"] == "character varying"
    assert legacy_types["created_date"] == "timestamp without time zone"
    assert _rows(engine) == [
        ("first", "True", datetime(2026, 10, 17, 8, 30)),
        ("second", "False", datetime(2026, 1, 2, 3, 4, 5)),
        ("third", "True", datetime(2025, 12, 31, 23, 59)),
    ]


def test_migration_refuses_unknown_completed_values(engine: sa.Engine) -> None:
    _create_legacy_table(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO note (title, description, prompt, completed, created_date) VALUES ('bad', 'desc', 'prompt', 'maybe', now())",
            ),
        )

    with pytest.raises(sa.exc.IntegrityError):
        _run(engine, "upgrade")

    # The failed transaction left the legacy schema untouched.
    assert _column_types(engine)["completed"] == "character varying"


@pytest_asyncio.fixture
async def database(
    engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Database]:
    _create_legacy_table(engine)
    _run(engine, "upgrade")
    db = Database(_async_url())
    await db.connect()
    monkeypatch.setattr(crud, "database", db)
    try:
        yield db
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_crud_roundtrip_after_migration(database: Database) -> None:
    paris = timezone(timedelta(hours=2))
    created = datetime(2026, 10, 17, 10, 30, tzinfo=paris)
    payload = NoteResponse(
        title="roundtrip",
        description="roundtrip description",
        type="note",
        prompt="roundtrip prompt",
        completed=True,
    )

    note_id = await crud.post(payload, created_date=created)
    stored = NoteData.from_record(await crud.get(note_id))

    assert stored.completed is True
    assert stored.created_date == datetime(2026, 10, 17, 8, 30, tzinfo=timezone.utc)
    assert stored.created_date.utcoffset() == timedelta(0)

    update = payload.model_copy(update={"completed": False, "title": "updated"})
    assert await crud.put(note_id, update) == note_id
    updated = NoteData.from_record(await crud.get(note_id))
    assert (updated.title, updated.completed) == ("updated", False)
    assert updated.created_date == stored.created_date

    legacy = [NoteData.from_record(row) for row in await crud.get_all()]
    assert [(note.title, note.completed) for note in legacy] == [
        ("first", True),
        ("second", False),
        ("third", True),
        ("updated", False),
    ]

    await crud.delete(note_id)
    assert await crud.get(note_id) is None
