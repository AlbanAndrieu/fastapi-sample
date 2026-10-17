"""Real PostgreSQL coverage for the full Alembic chain (baseline + notes).

Run only against a disposable database, for example::

    docker run --rm -d --name notes-pg -e POSTGRES_PASSWORD=<pw> \
        -p 127.0.0.1:55432:5432 postgres:17-alpine
    NOTES_POSTGRES_INTEGRATION_URL=postgresql://postgres:<pw>@127.0.0.1:55432/postgres \
        uv run pytest tests/integration/test_alembic_postgres.py -m integration

The tests drop and recreate the ``user``, ``note``, ``sensor_reading`` and
``alembic_version`` tables; never point them at a shared, staging or
production database.
"""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from nabla.api.db.metadata import application_metadata

_PG_URL = os.getenv("NOTES_POSTGRES_INTEGRATION_URL", "").strip()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _PG_URL,
        reason="NOTES_POSTGRES_INTEGRATION_URL is required for PostgreSQL Alembic tests",
    ),
]

_ROOT = Path(__file__).resolve().parents[2]
_OWNED_TABLES = ("alembic_version", "user", "note", "sensor_reading")
_BASELINE_TABLES = {"user", "note", "sensor_reading"}
_BASELINE_REVISION = "992855f73a8d"
_NOTES_REVISION = "4b7c2d9e1a6f"


def _sync_url() -> str:
    return make_url(_PG_URL).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _drop_owned_tables(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        for table in _OWNED_TABLES:
            connection.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = sa.create_engine(_sync_url())
    _drop_owned_tables(engine)
    try:
        yield engine
    finally:
        _drop_owned_tables(engine)
        engine.dispose()


def _alembic(engine: sa.Engine, action: str, revision: str) -> None:
    config = Config(str(_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, action)(config, revision)


def _head() -> str:
    head = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini"))).get_current_head()
    assert head is not None
    return head


def _current(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names()) & _BASELINE_TABLES


def _schema_diff(engine: sa.Engine) -> list[object]:
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "compare_server_default": True},
        )
        return list(compare_metadata(context, application_metadata()))


def test_head_is_the_notes_revision() -> None:
    assert _head() == _NOTES_REVISION


def test_upgrade_head_on_empty_database_matches_application_metadata(engine: sa.Engine) -> None:
    assert _tables(engine) == set()

    _alembic(engine, "upgrade", "head")

    assert _current(engine) == _NOTES_REVISION
    assert _tables(engine) == _BASELINE_TABLES
    assert _schema_diff(engine) == []

    _alembic(engine, "downgrade", "base")

    assert _current(engine) is None
    assert _tables(engine) == set()

    _alembic(engine, "upgrade", "head")

    assert _current(engine) == _NOTES_REVISION
    assert _schema_diff(engine) == []


@pytest.mark.parametrize("stamped", [_BASELINE_REVISION, _NOTES_REVISION])
def test_upgrade_head_keeps_create_all_database_and_rows(engine: sa.Engine, stamped: str) -> None:
    for metadata in application_metadata():
        metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO note (title, description, type, prompt, completed, created_date) VALUES ('keep', 'desc', 'note', 'prompt', TRUE, now())",
            ),
        )
    _alembic(engine, "stamp", stamped)

    _alembic(engine, "upgrade", "head")

    assert _current(engine) == _NOTES_REVISION
    assert _schema_diff(engine) == []
    with engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT title, completed FROM note")).all()
    assert [tuple(row) for row in rows] == [("keep", True)]


def test_baseline_upgrade_tolerates_unstamped_create_all_schema(engine: sa.Engine) -> None:
    for metadata in application_metadata():
        metadata.create_all(engine)

    _alembic(engine, "upgrade", "head")

    assert _current(engine) == _NOTES_REVISION
    assert _schema_diff(engine) == []
