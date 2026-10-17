"""note: completed as boolean and created_date as timestamptz

Revision ID: 4b7c2d9e1a6f
Revises: 992855f73a8d
Create Date: 2026-10-17 00:00:00

Legacy ``note`` rows stored ``completed`` as VARCHAR(8) ("True"/"False") and
``created_date`` as a naive TIMESTAMP written with the server clock (UTC in the
container images). The upgrade converts both columns in place:

``completed``: case-insensitive true/false spellings map to BOOLEAN. Any other
value aborts the migration (NOT NULL violation) instead of being silently
coerced; ``SELECT DISTINCT completed FROM note`` shows the offenders.

``created_date``: naive values are interpreted as UTC
(``created_date AT TIME ZONE 'UTC'``).

The downgrade restores the exact legacy representation ("True"/"False" and
the same naive UTC wall-clock values). Each step is skipped when the column
already has the target type (fresh databases created by ``create_all``) or
when the ``note`` table does not exist. ``ALTER COLUMN ... TYPE`` rewrites the
table under an ACCESS EXCLUSIVE lock; the notes table is small, but run it in
a maintenance window on large datasets.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b7c2d9e1a6f"
down_revision: Union[str, Sequence[str], None] = "992855f73a8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "note"
TRUE_SPELLINGS = ("true", "t", "1", "yes", "y", "on")
FALSE_SPELLINGS = ("false", "f", "0", "no", "n", "off")


BOOLEAN = "boolean"
AWARE_TIMESTAMP = "timestamp with time zone"


def _column_types() -> dict[str, str]:
    """Return ``note`` column data types (empty when the table is absent)."""
    rows = op.get_bind().execute(
        sa.text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = :table",
        ),
        {"table": TABLE},
    )
    return {str(name): str(data_type) for name, data_type in rows}


def _sql_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Convert legacy text booleans and naive timestamps."""
    types = _column_types()
    if not types:
        return

    if types.get("completed") != BOOLEAN:
        op.alter_column(TABLE, "completed", server_default=None)
        op.execute(
            f"ALTER TABLE {TABLE} ALTER COLUMN completed TYPE BOOLEAN USING "
            "CASE "
            f"WHEN lower(trim(completed)) IN ({_sql_list(TRUE_SPELLINGS)}) THEN TRUE "
            f"WHEN lower(trim(completed)) IN ({_sql_list(FALSE_SPELLINGS)}) THEN FALSE "
            "ELSE NULL END",
        )
        op.alter_column(TABLE, "completed", server_default=sa.false())

    if types.get("created_date") != AWARE_TIMESTAMP:
        op.execute(
            f"ALTER TABLE {TABLE} ALTER COLUMN created_date TYPE TIMESTAMP WITH TIME ZONE USING created_date AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Restore the legacy VARCHAR(8) boolean and naive UTC timestamp."""
    types = _column_types()
    if not types:
        return

    if types.get("created_date") == AWARE_TIMESTAMP:
        op.execute(
            f"ALTER TABLE {TABLE} ALTER COLUMN created_date TYPE TIMESTAMP WITHOUT TIME ZONE USING created_date AT TIME ZONE 'UTC'",
        )

    if types.get("completed") == BOOLEAN:
        op.alter_column(TABLE, "completed", server_default=None)
        op.execute(
            f"ALTER TABLE {TABLE} ALTER COLUMN completed TYPE VARCHAR(8) USING CASE WHEN completed THEN 'True' ELSE 'False' END",
        )
        # Legacy schemas had only the ORM-side default "False", no server default.
