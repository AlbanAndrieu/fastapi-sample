"""Deterministic SQL and transaction boundaries; no Slack/DB/network access."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from nabla.api.approvals.notification_outbox import (
    due_outbox,
    notification_outbox,
    outbox_insert,
    record_pending_and_outbox,
)


def test_outbox_sql_is_payload_free_idempotent_and_locked():
    stmt = outbox_insert(event_type="approval_requested", subject_sha256="a" * 64)
    code = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in code and "DO NOTHING" in code
    assert "token" not in notification_outbox.c
    assert "payload" not in notification_outbox.c
    assert "plan" not in notification_outbox.c
    assert "message" not in notification_outbox.c
    worker = str(due_outbox().compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in worker
    assert "LIMIT" in worker
    with pytest.raises(ValueError):
        outbox_insert(event_type="terraform_apply", subject_sha256="a" * 64)
    with pytest.raises(ValueError):
        outbox_insert(event_type="approval_requested", subject_sha256="invalid")
    with pytest.raises(ValueError):
        due_outbox(limit=0)


class _Database:
    def __init__(self, *, duplicate=False, fail_outbox=False):
        self.duplicate = duplicate
        self.fail_outbox = fail_outbox
        self.in_transaction = False
        self.committed = False
        self.rolled_back = False
        self.calls = []

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True
        finally:
            self.in_transaction = False

    async def fetch_val(self, *, query):
        assert self.in_transaction
        self.calls.append("approval")
        return None if self.duplicate else "a" * 64

    async def execute(self, *, query):
        assert self.in_transaction
        self.calls.append("outbox")
        if self.fail_outbox:
            raise RuntimeError("offline database failure")
        return 1


@pytest.mark.asyncio
async def test_transaction_commits_both_or_neither():
    now = datetime.now(timezone.utc)
    kwargs = {
        "challenge_sha256": "a" * 64,
        "commit_sha": "b" * 40,
        "plan_sha256": "c" * 64,
        "run_id": 1,
        "expires_at": now + timedelta(minutes=10),
        "now": now,
    }
    db = _Database()
    assert await record_pending_and_outbox(db, **kwargs) is True
    assert db.committed is True and db.calls == ["approval", "outbox"]
    duplicate = _Database(duplicate=True)
    assert await record_pending_and_outbox(duplicate, **kwargs) is False
    assert duplicate.calls == ["approval"]
    failing = _Database(fail_outbox=True)
    with pytest.raises(RuntimeError):
        await record_pending_and_outbox(failing, **kwargs)
    assert failing.rolled_back is True and not failing.committed
