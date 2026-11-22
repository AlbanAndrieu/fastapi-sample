"""Durable, payload-free notification outbox for the existing OpenClaw Slack App.

Only PostgreSQL commits can authorize delivery. No OpenClaw tokens or plan bodies.
This module deliberately does NOT implement delivery, signature verification,
workflow dispatch, Terraform apply, or approval state transitions.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import re

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from nabla.api.approvals.persistence import approval_metadata, approvals, pending_insert
from nabla.api.db.timestamps import utc_now

_ALLOWED_EVENTS = frozenset(
    {
        "approval_requested",
        "workflow_failed",
        "security_finding",
        "rss_relevant",
    },
)
_DIGEST = re.compile(r"[0-9a-f]{64}")

notification_outbox = sa.Table(
    "operation_notification_outbox",
    approval_metadata,
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


def outbox_insert(*, event_type: str, subject_sha256: str, now: datetime | None = None):
    """One deduplicated envelope containing no title, URL, token or plan data."""
    if event_type not in _ALLOWED_EVENTS or not isinstance(subject_sha256, str) or not _DIGEST.fullmatch(subject_sha256):
        raise ValueError("Invalid outbox event")
    now = now or utc_now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("UTC-aware event time required")
    digest = hashlib.sha256(
        ("nabla-outbox-v1\x00" + event_type + "\x00" + subject_sha256).encode(),
    ).hexdigest()
    return (
        insert(notification_outbox)
        .values(
            event_sha256=digest,
            event_type=event_type,
            subject_sha256=subject_sha256,
            destination="nabla-openclaw",
            delivery_state="pending",
            attempts=0,
            created_at=now,
            not_before=now,
            sent_at=None,
        )
        .on_conflict_do_nothing(index_elements=[notification_outbox.c.event_sha256])
    )


def due_outbox(*, now: datetime | None = None, limit: int = 20):
    """For a future isolated worker only; lock rows inside a DB transaction."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Invalid outbox batch size")
    now = now or utc_now()
    return (
        sa.select(notification_outbox)
        .where(
            notification_outbox.c.delivery_state == "pending",
            notification_outbox.c.attempts < 5,
            notification_outbox.c.not_before <= now,
        )
        .order_by(notification_outbox.c.created_at, notification_outbox.c.event_sha256)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


async def record_pending_and_outbox(
    database,
    *,
    challenge_sha256: str,
    commit_sha: str,
    plan_sha256: str,
    run_id: int,
    expires_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Atomic insert+outbox if a separate trusted worker verified provenance.

    Does NOT validate a YubiKey signature and MUST NOT be exposed as an HTTP
    mutation. A duplicate approval creates no notification and replay is inert.
    """
    now = now or utc_now()
    stmt = pending_insert(
        challenge_sha256=challenge_sha256,
        commit_sha=commit_sha,
        plan_sha256=plan_sha256,
        run_id=run_id,
        expires_at=expires_at,
        now=now,
    ).returning(approvals.c.challenge_sha256)
    async with database.transaction():
        inserted = await database.fetch_val(query=stmt)
        if inserted is None:
            return False
        await database.execute(
            query=outbox_insert(
                event_type="approval_requested",
                subject_sha256=challenge_sha256,
                now=now,
            ),
        )
    return True
