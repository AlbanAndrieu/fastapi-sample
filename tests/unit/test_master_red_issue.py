"""No-runner, no-network contracts for rolling master-red issue updates."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/master_red_issue.py"
spec = importlib.util.spec_from_file_location("master_red_issue_tracker", SCRIPT)
assert spec and spec.loader
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)
GREEN = dict.fromkeys(tracker.STATUS_KEYS, "success")
RED = {**GREEN, "PYTHON": "failure"}
SHA = "a" * 40


class FakeGitHub:
    def __init__(self, events=None):
        self.issue = {
            "number": 355,
            "title": "[master-red] Suivi unique de la dernière gate master",
            "body": "Manual operational analysis retained",
            "labels": [],
            "assignees": [],
            "milestone": None,
            "state": "open",
            "updated_at": tracker.ENROLLMENT_UPDATED_AT,
        }
        # Default: an issue never touched by a human. Manual history is
        # injected explicitly by the tests that exercise the override rule.
        self.events = events if events is not None else []
        self.comments = []
        self.actions = []

    def __call__(self, method, route, data=None):
        self.actions.append((method, route, data))
        if route.endswith("/commits/master"):
            return {"sha": SHA}
        if route.endswith("/issues/355/events?per_page=100"):
            return self.events
        if route.endswith("/issues/355/comments?per_page=100") and method == "GET":
            return self.comments
        if route.endswith("/issues/355") and method == "GET":
            return dict(self.issue)
        if route.endswith("/issues/355/comments") and method == "POST":
            self.comments.append(
                {
                    "id": 18,
                    "user": {"login": "github-actions[bot]"},
                    "body": data["body"],
                    "created_at": "2026-10-19T20:00:00Z",
                },
            )
            return self.comments[-1]
        if route.endswith("/issues/comments/18") and method == "PATCH":
            self.comments[0]["body"] = data["body"]
            return self.comments[0]
        if route.endswith("/issues/355") and method == "PATCH":
            self.issue["state"] = data["state"]
            return dict(self.issue)
        raise AssertionError(f"unapproved fake request: {method} {route}")


class MasterRedTrackerTests(unittest.TestCase):
    def test_one_comment_reused_and_closed_only_after_two_green_runs(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            self.assertIn("RED", tracker.reconcile(100, SHA, RED))
            self.assertEqual(fake.issue["state"], "open")
            self.assertIn("successes=1", tracker.reconcile(101, SHA, GREEN))
            self.assertEqual(fake.issue["state"], "open")
            self.assertIn("two consecutive", tracker.reconcile(102, SHA, GREEN))
        self.assertEqual(fake.issue["state"], "closed")
        self.assertEqual(len(fake.comments), 1)
        self.assertFalse(
            any(action[0] == "POST" and action[1].endswith("/issues") for action in fake.actions),
        )
        self.assertFalse(any("pulls" in action[1] for action in fake.actions))
        self.assertFalse(
            any(action[2] and ("title" in action[2] or "labels" in action[2]) for action in fake.actions),
        )

    def test_latest_failure_resets_consecutive_green_counter(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(50, SHA, GREEN)
            tracker.reconcile(51, SHA, RED)
            tracker.reconcile(52, SHA, GREEN)
        self.assertEqual(fake.issue["state"], "open")
        self.assertEqual(tracker.parse_comment(fake.comments[0])["green_streak"], 1)

    def test_manual_issue_edit_blocks_subsequent_bot_mutations(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            fake.issue["body"] = "Manually reviewed and annotated"
            original = fake.comments[0]["body"]
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(101, SHA, GREEN))
            self.assertEqual(fake.comments[0]["body"], original)
            self.assertEqual(fake.issue["state"], "open")

    def test_manual_label_event_freezes_open_issue_even_if_reverted(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            first_comment = fake.comments[0]["body"]
            fake.events.append(
                {
                    "event": "labeled",
                    "actor": {"login": "AlbanAndrieu"},
                    "created_at": "2026-10-19T21:00:00Z",
                },
            )
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(101, SHA, GREEN))
        self.assertEqual(fake.comments[0]["body"], first_comment)

    def test_manual_comment_edit_is_preserved(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            fake.comments[0]["body"] += " human note"
            with self.assertRaises(tracker.TrackerError):
                tracker.reconcile(101, SHA, GREEN)

    def test_manual_rename_prevents_any_reopening_after_closed(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, GREEN)
            tracker.reconcile(101, SHA, GREEN)
            fake.events.append(
                {
                    "event": "renamed",
                    "actor": {"login": "AlbanAndrieu"},
                    "created_at": "2026-10-19T21:00:00Z",
                },
            )
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(102, SHA, RED))
        self.assertEqual(fake.issue["state"], "closed")

    def test_automatically_closed_unmodified_issue_can_be_reopened(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, GREEN)
            tracker.reconcile(101, SHA, GREEN)
            self.assertIn("REOPENED", tracker.reconcile(102, SHA, RED))
        self.assertEqual(fake.issue["state"], "open")

    def test_manual_close_after_tracker_comment_is_never_reopened(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            fake.issue["state"] = "closed"
            fake.events.append(
                {
                    "event": "closed",
                    "actor": {"login": "AlbanAndrieu"},
                    "created_at": "2026-10-19T21:00:00Z",
                },
            )
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(101, SHA, RED))
        self.assertEqual(fake.issue["state"], "closed")

    def test_manual_label_reverted_still_blocks_reopen(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, GREEN)
            tracker.reconcile(101, SHA, GREEN)
            fake.events.append(
                {
                    "event": "unlabeled",
                    "actor": {"login": "AlbanAndrieu"},
                    "created_at": "2026-10-19T21:30:00Z",
                },
            )
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(102, SHA, RED))
        self.assertEqual(fake.issue["state"], "closed")

    def test_issue_closed_before_enrollment_is_never_reopened(self):
        fake = FakeGitHub(events=[])
        fake.issue["state"] = "closed"
        with patch.object(tracker, "github", side_effect=fake):
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(100, SHA, RED))
        self.assertEqual(fake.comments, [])
        self.assertEqual(fake.issue["state"], "closed")

    def test_stale_or_duplicate_run_never_writes(self):
        fake = FakeGitHub()
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            n = len(fake.actions)
            self.assertIn("STALE", tracker.reconcile(100, SHA, GREEN))
            self.assertTrue(all(method == "GET" for method, _, _ in fake.actions[n:]))
        with patch.object(tracker, "github", return_value={"sha": "b" * 40}) as gh:
            self.assertIn("STALE", tracker.reconcile(101, SHA, GREEN))
            self.assertEqual(gh.call_count, 1)

    def test_required_skipped_zap_is_not_green(self):
        self.assertFalse(
            tracker.green(
                {**GREEN, "ZAP": "skipped"},
                {"CODEQL": False, "ZAP": True},
            ),
        )
        self.assertTrue(
            tracker.green(
                {**GREEN, "ZAP": "skipped"},
                {"CODEQL": False, "ZAP": False},
            ),
        )

    def test_intervening_manual_edit_prevents_status_comment_creation(self):
        fake = FakeGitHub(events=[])
        original_api = fake.__call__
        master_reads = 0

        def concurrent_edit(method, route, data=None):
            nonlocal master_reads
            if route.endswith("/commits/master"):
                master_reads += 1
                if master_reads == 2:
                    fake.issue["body"] = "Human modified during reconciliation"
            return original_api(method, route, data)

        with patch.object(tracker, "github", side_effect=concurrent_edit):
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(100, SHA, RED))
        self.assertEqual(fake.comments, [])
        self.assertFalse(any(method in ("POST", "PATCH") for method, _, _ in fake.actions))

    def test_schema_fails_closed(self):
        with self.assertRaises(tracker.TrackerError):
            tracker.reconcile(1, SHA, {"PYTHON": "success"})
        bad = {**GREEN, "ZAP": "unexpected"}
        with self.assertRaises(tracker.TrackerError):
            tracker.reconcile(1, SHA, bad)

    def test_enrollment_stops_on_any_manual_edit_before_first_bot_comment(self):
        fake = FakeGitHub()
        fake.issue["updated_at"] = "2026-10-20T05:00:00Z"
        with patch.object(tracker, "github", side_effect=fake):
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(100, SHA, RED))
        self.assertEqual(fake.comments, [])
        self.assertFalse(any(action[0] in ("POST", "PATCH") for action in fake.actions))

    def test_human_comment_after_enrollment_freezes_bot_updates(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, RED)
            original = fake.comments[0]["body"]
            fake.comments.append(
                {
                    "id": 19,
                    "user": {"login": "AlbanAndrieu"},
                    "body": "Human investigation; preserve",
                    "created_at": "2026-10-19T21:30:00Z",
                },
            )
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(101, SHA, GREEN))
        self.assertEqual(fake.comments[0]["body"], original)
        self.assertEqual(fake.issue["state"], "open")

    def test_pre_enrollment_human_comment_disables_bot_ownership(self):
        fake = FakeGitHub()
        fake.comments.append({
            "id": 77,
            "body": "Operator investigation predates enrollment",
            "user": {"login": "AlbanAndrieu"},
            "created_at": "2026-10-19T20:00:00Z",
        })
        with patch.object(tracker, "github", side_effect=fake):
            self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(100, SHA, RED))
        self.assertEqual(len(fake.comments), 1)
        self.assertFalse(any(
            method in ("POST", "PATCH") for method, _, _ in fake.actions
        ))

    def test_manually_touched_issue_is_never_closed_by_the_bot(self):
        fake = FakeGitHub(
            events=[
                {
                    "event": "renamed",
                    "actor": {"login": "AlbanAndrieu"},
                    "created_at": "2026-10-19T20:46:58Z",
                },
            ],
        )
        with patch.object(tracker, "github", side_effect=fake):
            for run_id in (100, 101, 102):
                self.assertIn("MANUAL_OVERRIDE", tracker.reconcile(run_id, SHA, GREEN))
        self.assertEqual(fake.issue["state"], "open")
        self.assertFalse(
            any(action[0] == "PATCH" and action[1].endswith("/issues/355") for action in fake.actions),
        )

    def test_missing_run_between_two_green_results_resets_streak(self):
        fake = FakeGitHub(events=[])
        with patch.object(tracker, "github", side_effect=fake):
            tracker.reconcile(100, SHA, GREEN, run_number=80)
            tracker.reconcile(103, SHA, GREEN, run_number=82)
        self.assertEqual(fake.issue["state"], "open")
        self.assertEqual(tracker.parse_comment(fake.comments[0])["green_streak"], 1)


def test_workflow_no_creating_per_sha_issues_or_draft_prs():
    workflow = (ROOT / ".github/workflows/master-red-remediation.yml").read_text()
    assert "gh issue create" not in workflow
    assert "gh pr create" not in workflow
    assert "scripts/ci/master_red_issue.py --apply" in workflow
    assert "issues: write" in workflow


if __name__ == "__main__":
    unittest.main()
