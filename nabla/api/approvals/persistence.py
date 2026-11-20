"""Persistent pending approval inventory. No authority to approve or execute."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from nabla.api.db.timestamps import utc_now

approval_metadata = sa.MetaData()
approvals = sa.Table(
    "operation_approval",
    approval_metadata,
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


def pending_insert(
    *, challenge_sha256: str, commit_sha: str, plan_sha256: str,
    run_id: int, expires_at: datetime, now: datetime | None = None,
):
    """Only the existing Entra pilot; duplicate challenge is a no-op.

    The caller must obtain and verify the original challenge; no endpoint or
    worker is wired until durable signature and single-consumption contracts.
    """
    now = now or utc_now()
    for value, length in ((challenge_sha256, 64), (commit_sha, 40), (plan_sha256, 64)):
        if not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value):
            raise ValueError("invalid digest")
    if type(run_id) is not int or not 0 < run_id < 2**63:
        raise ValueError("invalid run")
    if expires_at.tzinfo is None or not now < expires_at <= now + timedelta(minutes=90):
        raise ValueError("invalid expiry")
    return insert(approvals).values(
        challenge_sha256=challenge_sha256, repository="AlbanAndrieu/nabla-compose",
        workflow="entra.yml", commit_sha=commit_sha, plan_sha256=plan_sha256,
        run_id=run_id, created_at=now, expires_at=expires_at, state="pending",
    ).on_conflict_do_nothing(index_elements=[approvals.c.challenge_sha256])


def pending_list(*, limit: int = 50, now: datetime | None = None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("invalid page size")
    return (sa.select(approvals)
            .where(approvals.c.state == 'pending', approvals.c.expires_at > (now or utc_now()))
            .order_by(approvals.c.created_at.desc(), approvals.c.challenge_sha256)
            .limit(limit))
