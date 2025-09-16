"""create user table

Revision ID: 992855f73a8d
Revises:
Create Date: 2025-09-16 09:51:25.144440

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "992855f73a8d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# See https://alembic.sqlalchemy.org/en/latest/tutorial.html
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("email", sa.String(50), nullable=False),
        sa.Column("description", sa.Unicode(200)),
    )

    op.add_column("user", sa.Column("created_at", sa.DateTime))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user")
