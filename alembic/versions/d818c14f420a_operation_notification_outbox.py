"""Payload-free PostgreSQL notification outbox for controlled approvals.

Revision ID: d818c14f420a
Revises: 82db3b1f90a2
"""

import sqlalchemy as sa
from alembic import op

revision = "d818c14f420a"
down_revision = "82db3b1f90a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("operation_notification_outbox"):
        return
    op.create_table(
        "operation_notification_outbox",
        sa.Column("event_sha256", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("subject_sha256", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(24), server_default="nabla-openclaw", nullable=False),
        sa.Column("delivery_state", sa.String(12), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('approval_requested','workflow_failed','security_finding','rss_relevant')",
            name="ck_notification_outbox_event_type",
        ),
        sa.CheckConstraint(
            "delivery_state IN ('pending','sent','dead')",
            name="ck_notification_outbox_state",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_notification_outbox_attempts"),
        sa.CheckConstraint("not_before >= created_at", name="ck_notification_outbox_schedule"),
    )


def downgrade() -> None:
    op.drop_table("operation_notification_outbox")
