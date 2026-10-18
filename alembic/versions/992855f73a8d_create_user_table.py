"""create user table (baseline schema)

Revision ID: 992855f73a8d
Revises:
Create Date: 2025-09-16 09:51:25.144440

Baseline of the schema the application historically created with
``Base.metadata.create_all`` at startup (``user``, ``note`` and
``sensor_reading``).

The original revision only created a legacy integer-keyed ``user`` table and
then altered a ``note`` table it never created, so ``alembic upgrade head``
failed on an empty database and the whole transaction rolled back: no database
can have recorded this revision by running it. Existing deployments were built
by ``create_all`` and stamped instead, so they never execute this upgrade.

The upgrade is therefore tolerant and non-destructive:

1. Every table and index is created only when absent, with the shape produced
by ``create_all`` (``user`` follows the fastapi-users UUID model the
application requires).
2. ``note`` is created in its legacy representation (``completed`` VARCHAR(8),
naive ``created_date``) so that revision ``4b7c2d9e1a6f`` performs the
conversion exactly as it does for older databases.
3. On a pre-existing ``note`` table only the missing ``type``/``prompt`` columns
are added, as the original revision intended.

The downgrade drops the three baseline tables when present; it is meant for
disposable databases (``alembic downgrade base``), never for shared data.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "992855f73a8d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BASELINE_TABLES = ("user", "note", "sensor_reading")


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table)}


def _create_user() -> None:
    op.create_table(
        "user",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True, if_not_exists=True)


def _create_legacy_note() -> None:
    op.create_table(
        "note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=50), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("prompt", sa.String(length=100), nullable=False),
        # Legacy representation, converted by revision 4b7c2d9e1a6f.
        sa.Column("completed", sa.String(length=8), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_id", "note", ["id"], if_not_exists=True)


def _create_sensor_reading() -> None:
    op.create_table(
        "sensor_reading",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("humidity", sa.Float(), nullable=False),
        sa.Column("pressure", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_reading_id", "sensor_reading", ["id"], if_not_exists=True)


def upgrade() -> None:
    """Create the baseline tables that are missing; never alter existing data."""
    if not _has_table("user"):
        _create_user()

    if not _has_table("note"):
        _create_legacy_note()
    else:
        existing = _column_names("note")
        if "type" not in existing:
            op.add_column("note", sa.Column("type", sa.String(10), nullable=False))
        if "prompt" not in existing:
            op.add_column("note", sa.Column("prompt", sa.String(100), nullable=False))

    if not _has_table("sensor_reading"):
        _create_sensor_reading()


def downgrade() -> None:
    """Drop the baseline tables (disposable databases only)."""
    for table in BASELINE_TABLES:
        op.drop_table(table, if_exists=True)
