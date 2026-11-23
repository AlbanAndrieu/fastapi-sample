"""Real PostgreSQL contracts for the F15/F18 approval outbox.

Covers what fakes cannot: duplicate inserts, transactional rollback on a real
CHECK violation, FOR UPDATE SKIP LOCKED between two workers, and expiry.
Uses the same disposable database variable as ``test_alembic_postgres.py``
(``NOTES_POSTGRES_INTEGRATION_URL``) and drops the approval tables: never point
it at a shared, staging or production database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
import hashlib
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from databases import Database
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from nabla.api.approvals import notification_outbox as outbox
from nabla.api.approvals.persistence import pending_insert, pending_list
from nabla.api.db.timestamps import utc_now

_PG_URL = os.getenv("NOTES_POSTGRES_INTEGRATION_URL", "").strip()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _PG_URL,
        reason="NOTES_POSTGRES_INTEGRATION_URL is required for PostgreSQL outbox tests",
    ),
]

_ROOT = Path(__file__).resolve().parents[2]
_OWNED_TABLES = ("alembic_version", "user", "note", "sensor_reading", "operation_notification_outbox", "operation_approval")


def _url(driver: str) -> str:
    return make_url(_PG_URL).set(drivername=driver).render_as_string(hide_password=False)


def _drop_owned_tables(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        for table in _OWNED_TABLES:
            connection.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = sa.create_engine(_url("postgresql+psycopg"))
    _drop_owned_tables(engine)
    config = Config(str(_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    try:
        yield engine
    finally:
        _drop_owned_tables(engine)
        engine.dispose()


@pytest_asyncio.fixture
async def database(engine: sa.Engine) -> AsyncIterator[Database]:
    database = Database(_url("postgresql+asyncpg"))
    await database.connect()
    try:
        yield database
    finally:
        await database.disconnect()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(sa.select(sa.func.count()).select_from(sa.table(table))).scalar_one()


async def _record(database: Database, label: str, now) -> bool:
    return await outbox.record_pending_and_outbox(
        database,
        challenge_sha256=_digest(label),
        commit_sha="a" * 40,
        plan_sha256=_digest(f"plan-{label}"),
        run_id=1,
        expires_at=now + timedelta(minutes=30),
        now=now,
    )


@pytest.mark.asyncio
async def test_duplicate_approval_and_outbox_event_are_inert(engine: sa.Engine, database: Database) -> None:
    now = utc_now()

    assert await _record(database, "duplicate", now) is True
    assert await _record(database, "duplicate", now) is False
    with engine.begin() as connection:
        connection.execute(outbox.outbox_insert(event_type="approval_requested", subject_sha256=_digest("duplicate"), now=now))

    assert _count(engine, "operation_approval") == 1
    assert _count(engine, "operation_notification_outbox") == 1


@pytest.mark.asyncio
async def test_outbox_check_violation_rolls_back_the_approval(engine: sa.Engine, database: Database, monkeypatch) -> None:
    real_insert = outbox.outbox_insert

    def violating_insert(**kwargs):
        # A delivery scheduled before creation breaks ck_notification_outbox_schedule.
        return real_insert(**kwargs).values(not_before=kwargs["now"] - timedelta(seconds=1))

    monkeypatch.setattr(outbox, "outbox_insert", violating_insert)

    with pytest.raises(Exception, match="ck_notification_outbox_schedule"):
        await _record(database, "rollback", utc_now())

    assert _count(engine, "operation_approval") == 0
    assert _count(engine, "operation_notification_outbox") == 0


def test_two_workers_never_claim_the_same_outbox_row(engine: sa.Engine) -> None:
    created = utc_now() - timedelta(seconds=5)
    with engine.begin() as connection:
        for label in ("first", "second"):
            connection.execute(outbox.outbox_insert(event_type="workflow_failed", subject_sha256=_digest(label), now=created))

    worker_a, worker_b, observer = engine.connect(), engine.connect(), engine.connect()
    try:
        worker_a.begin()
        worker_b.begin()
        claimed_a = worker_a.execute(outbox.due_outbox(limit=1)).all()
        claimed_b = worker_b.execute(outbox.due_outbox(limit=1)).all()
        with observer.begin():
            claimed_while_locked = observer.execute(outbox.due_outbox(limit=50)).all()

        assert len(claimed_a) == len(claimed_b) == 1
        assert claimed_a[0].event_sha256 != claimed_b[0].event_sha256
        assert claimed_while_locked == []
    finally:
        for connection in (worker_a, worker_b, observer):
            connection.rollback()
            connection.close()

    with engine.connect() as connection:
        assert len(connection.execute(outbox.due_outbox(limit=50)).all()) == 2


def test_expired_pending_approval_is_never_listed(engine: sa.Engine) -> None:
    created = utc_now() - timedelta(hours=2)
    with engine.begin() as connection:
        connection.execute(
            pending_insert(
                challenge_sha256=_digest("expired"),
                commit_sha="b" * 40,
                plan_sha256=_digest("plan-expired"),
                run_id=2,
                expires_at=created + timedelta(minutes=30),
                now=created,
            ),
        )

    with engine.connect() as connection:
        assert connection.execute(pending_list()).all() == []
        assert len(connection.execute(pending_list(now=created + timedelta(minutes=1))).all()) == 1
