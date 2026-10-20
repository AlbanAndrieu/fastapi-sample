"""No issue churn after manual edits; keep run state fail-closed."""

from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts/ci/master_red_issue.py"
SPEC = importlib.util.spec_from_file_location("tracker", PATH)
assert SPEC and SPEC.loader
tracker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tracker)

SHA = "a" * 40
GREEN = dict.fromkeys(tracker.STATUS_KEYS, "success")
RED = {**GREEN, "PYTHON": "failure"}
REQUIRED = {"CODEQL": True, "ZAP": True}


class SingleTrackerTests(unittest.TestCase):
    def test_manual_rename_never_creates_comment_or_changes_issue(self):
        issue = {
            "number": 355,
            "state": "open",
            "title": "[master-red] reviewed by human",
            "body": "Manually curated report",
            "labels": [],
            "assignees": [],
            "milestone": None,
            "updated_at": tracker.ENROLLMENT_UPDATED_AT,
        }
        events = [
            {
                "event": "renamed",
                "actor": {"login": "AlbanAndrieu"},
                "created_at": "2026-10-19T21:03:15Z",
            },
        ]

        def api(method, route, data=None):
            self.assertEqual(method, "GET", "mutation forbidden")
            if route.endswith("/commits/master"):
                return {"sha": SHA}
            if route.endswith("/events?per_page=100"):
                return events
            if route.endswith("/comments?per_page=100"):
                return []
            return issue

        with mock.patch.object(tracker, "github", side_effect=api) as github:
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(99, SHA, RED, REQUIRED, 99))
            self.assertTrue(all(x.args[0] == "GET" for x in github.call_args_list))

    def test_two_success_runs_are_required(self):
        self.assertTrue(tracker.green(GREEN, REQUIRED))
        self.assertFalse(tracker.green({**GREEN, "ZAP": "skipped"}, REQUIRED))
        self.assertTrue(
            tracker.green(
                {**GREEN, "ZAP": "skipped"},
                {"CODEQL": True, "ZAP": False},
            ),
        )

    def test_human_event_is_sticky(self):
        events = [
            {
                "event": "renamed",
                "actor": {"login": "AlbanAndrieu"},
                "created_at": tracker.ENROLLMENT_UPDATED_AT,
            },
        ]
        self.assertTrue(tracker.manually_modified(events, None))


if __name__ == "__main__":
    unittest.main()
