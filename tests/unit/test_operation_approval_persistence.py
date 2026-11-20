from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from nabla.api.approvals.persistence import pending_insert, pending_list


def test_pending_only_idempotent_insert_and_bounded_list():
    now = datetime.now(timezone.utc)
    statement = pending_insert(challenge_sha256="a"*64, commit_sha="b"*40, plan_sha256="c"*64,
                               run_id=1, expires_at=now+timedelta(minutes=30), now=now)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql and "DO NOTHING" in sql
    assert "LIMIT" in str(pending_list())
    with pytest.raises(ValueError):
        pending_list(limit=1000)
    with pytest.raises(ValueError):
        pending_insert(challenge_sha256="a"*64, commit_sha="b"*40, plan_sha256="c"*64,
                       run_id=1, expires_at=now, now=now)
