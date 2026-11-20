"""Add pending-only operation approval inventory.

Revision ID: 82db3b1f90a2
Revises: 4b7c2d9e1a6f
"""
import sqlalchemy as sa
from alembic import op

revision = "82db3b1f90a2"
down_revision = "4b7c2d9e1a6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("operation_approval"):
        return
    op.create_table(
        "operation_approval",
        sa.Column("challenge_sha256", sa.String(64), primary_key=True),
        sa.Column("repository", sa.String(128), nullable=False),
        sa.Column("workflow", sa.String(64), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), server_default="pending", nullable=False),
        sa.CheckConstraint("state = 'pending'", name="ck_operation_approval_pending_only"),
        sa.CheckConstraint("expires_at > created_at", name="ck_operation_approval_expiry"),
        sa.CheckConstraint("run_id > 0", name="ck_operation_approval_run_id"),
    )


def downgrade() -> None:
    op.drop_table("operation_approval")
