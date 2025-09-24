"""create user table

Revision ID: 992855f73a8d
Revises:
Create Date: 2025-09-16 09:51:25.144440

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "992855f73a8d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# See https://alembic.sqlalchemy.org/en/latest/tutorial.html
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("email", sa.String(50), nullable=False),
        sa.Column("description", sa.Unicode(200)),
    )

    op.add_column("users", sa.Column("created_at", sa.DateTime))

    op.add_column('notes', sa.Column('type', sa.String(10), nullable=False))
    op.add_column('notes', sa.Column('prompt', sa.String(100), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")
