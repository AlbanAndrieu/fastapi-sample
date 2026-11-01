"""Actions usage aggregation must stay read-only and count only real evidence."""

from __future__ import annotations

import collections
import datetime as dt
import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "github-actions-usage.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("github_actions_usage", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_repo_sums_jobs_and_live_artifacts_with_run_cap(monkeypatch) -> None:
    module = load_module()
    responses = {
        "workflow_runs": [{"id": 1, "name": "CI"}, {"id": 2, "name": "CI"}, {"id": 3, "name": "Late"}],
        "artifacts": [{"size_in_bytes": 1048576}, {"size_in_bytes": 1048576, "expired": True}],
        "jobs": [
            {"started_at": "2026-11-01T00:00:00Z", "completed_at": "2026-11-01T00:03:00Z"},
            {"conclusion": "skipped", "started_at": None, "completed_at": None},
        ],
    }
    monkeypatch.setattr(module, "items", lambda path, key: responses[key])
    total = collections.defaultdict(lambda: {"runs": 0, "job_wall_minutes": 0.0, "artifact_mib": 0.0, "skipped_jobs": 0})

    module.collect_repo("owner/repo", dt.datetime(2026, 10, 1, tzinfo=dt.UTC), 2, total)

    assert dict(total) == {
        "owner/repo :: stored artifacts": {"runs": 0, "job_wall_minutes": 0.0, "artifact_mib": 1.0, "skipped_jobs": 0},
        "owner/repo :: CI": {"runs": 2, "job_wall_minutes": 6.0, "artifact_mib": 0.0, "skipped_jobs": 2},
    }
