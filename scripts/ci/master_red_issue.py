#!/usr/bin/env python3
"""Single rolling master-red tracker, without per-SHA issues or draft PRs.

The issue title/body/labels always remain under human control. Automation
owns exactly one verifiable status comment. Two distinct consecutive green
post-merge runs close the issue. Manual edits never get overwritten.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
import json
import os
import re
import subprocess
import sys

REPOSITORY = "AlbanAndrieu/fastapi-sample"
ISSUE = 355
# First opt-in is allowed only against the reviewed manually curated issue.
# Any intervening edit (including a reverted title/body) cancels adoption.
ENROLLMENT_UPDATED_AT = "2026-10-19T21:03:15Z"
MARKER = "<!-- nabla-master-red-tracker-v1 "
STATUS_KEYS = ("CLASSIFY", "PYTHON", "PRODUCTION_SMOKE", "CODEQL", "ZAP")
RESULTS = frozenset(
    {
        "success",
        "failure",
        "cancelled",
        "skipped",
        "timed_out",
        "neutral",
        "action_required",
    },
)
MANUAL_EVENTS = frozenset(
    {
        "edited",
        "renamed",
        "labeled",
        "unlabeled",
        "assigned",
        "unassigned",
        "closed",
        "reopened",
        "milestoned",
        "demilestoned",
        "locked",
        "unlocked",
    },
)


class TrackerError(ValueError):
    """Controlled fail-closed error without tokens or response bodies."""


def github(method: str, route: str, data: dict | None = None):
    if not route.startswith(f"repos/{REPOSITORY}/"):
        raise TrackerError("unapproved GitHub route")
    cmd = [
        "gh",
        "api",
        "--method",
        method,
        "-H",
        "Accept: application/vnd.github+json",
        route,
    ]
    if data is not None:
        cmd += ["--input", "-"]
    try:
        result = subprocess.run(
            cmd,
            input=json.dumps(data) if data is not None else None,
            text=True,
            capture_output=True,
            check=True,
            timeout=25,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        raise TrackerError("GitHub API request or response invalid") from None


def issue_fingerprint(issue: dict) -> str:
    """Ignore updated_at/comments: bot comments must not look like human edits."""
    fields = {
        "title": issue.get("title"),
        "body": issue.get("body") or "",
        "labels": sorted(label.get("name", "") for label in (issue.get("labels") or [])),
        "assignees": sorted(person.get("login", "") for person in (issue.get("assignees") or [])),
        "milestone": (issue.get("milestone") or {}).get("number"),
    }
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, ensure_ascii=True).encode(),
    ).hexdigest()


def render(state: dict) -> str:
    """Exact round trip acts as an integrity check for the bot-owned comment."""
    data = json.dumps(state, sort_keys=True, separators=(",", ":"))
    values = state["results"]
    detail = "\n".join(f"- {key}: `{values[key]}`" for key in STATUS_KEYS)
    return (
        f"{MARKER}{data} -->\n"
        "## Master post-merge · statut automatisé unique\n\n"
        f"- Dernier run : https://github.com/{REPOSITORY}/actions/runs/{state['run_id']}\n"
        f"- Commit : `{state['sha']}`\n"
        f"- État : **{state['result']}**\n"
        f"- Succès consécutifs : **{state['green_streak']}/2**\n"
        f"{detail}\n\n"
        "Le titre, les labels et la description de l'issue sont préservés. "
        "Les checks ignorés ne prouvent pas que les incidents historiques "
        "ont été corrigés. Deux runs post-merge verts sont requis avant clôture.\n"
    )


def parse_comment(comment: dict) -> dict:
    if not str(comment.get("body", "")).startswith(MARKER):
        raise TrackerError("unexpected tracker comment")
    author = (comment.get("user") or {}).get("login", "")
    if author != "github-actions[bot]":
        raise TrackerError("tracker status comment manually owned")
    match = re.match(
        r"^<!-- nabla-master-red-tracker-v1 (\{[^\n]+\}) -->\n",
        comment["body"],
    )
    if match is None:
        raise TrackerError("tracker metadata missing")
    try:
        state = json.loads(match.group(1))
    except ValueError:
        raise TrackerError("invalid tracker state") from None
    expected = {
        "fingerprint",
        "run_id",
        "run_number",
        "green_streak",
        "sha",
        "result",
        "results",
        "required",
    }
    if (
        not isinstance(state, dict)
        or set(state) != expected
        or not isinstance(state["run_id"], int)
        or not isinstance(state["run_number"], int)
        or not 0 <= state["green_streak"] <= 2
        or state["result"] not in ("RED", "GREEN")
        or set(state["results"]) != set(STATUS_KEYS)
        or state["required"].keys() != {"CODEQL", "ZAP"}
        or any(type(value) is not bool for value in state["required"].values())
        or not isinstance(state["fingerprint"], str)
        or re.fullmatch(r"[0-9a-f]{64}", state["fingerprint"]) is None
        or not isinstance(state["sha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", state["sha"]) is None
        or any(value not in RESULTS for value in state["results"].values())
        or render(state) != comment["body"]
    ):
        raise TrackerError("tracker status comment changed outside automation")
    return state


def manually_modified(events: list, since: str | None) -> bool:
    """Only events *after* bot enrollment affect whether it may reopen.

    Old manual edits belong to the original human-curated issue. Missing
    timestamps fail closed rather than assuming an event predates the bot.
    """
    if since is None:
        # Historical human ownership also blocks any future automatic reopen.
        return any(isinstance(event, dict) and event.get("event") in MANUAL_EVENTS and (event.get("actor") or {}).get("login") != "github-actions[bot]" for event in events)
    try:
        started = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        return True
    for event in events:
        if not isinstance(event, dict) or event.get("event") not in MANUAL_EVENTS:
            continue
        when = event.get("created_at")
        if not isinstance(when, str):
            return True
        try:
            later = datetime.fromisoformat(when.replace("Z", "+00:00")) > started
        except (TypeError, ValueError):
            return True
        if later and (event.get("actor") or {}).get("login") != "github-actions[bot]":
            return True
    return False


def green(results: dict, required: dict) -> bool:
    return all(
        results[key] == "success"
        for key in (
            "CLASSIFY",
            "PYTHON",
            "PRODUCTION_SMOKE",
        )
    ) and all(results[key] == "success" or (not required[key] and results[key] == "skipped") for key in ("CODEQL", "ZAP"))


def _validate_run(run_id: int, sha: str, results: dict, required: dict, run_number: int) -> None:
    if set(required) != {"CODEQL", "ZAP"} or any(type(x) is not bool for x in required.values()):
        raise TrackerError("required gate contract invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or run_id <= 0 or run_number <= 0:
        raise TrackerError("run metadata is invalid")
    if set(results) != set(STATUS_KEYS) or any(value not in RESULTS for value in results.values()):
        raise TrackerError("unrecognized gate result")


def _bounded_list(route: str, message: str) -> list:
    items = github("GET", route)
    if not isinstance(items, list) or len(items) == 100:
        raise TrackerError(message)
    return items


def _timestamp(value: object, missing: str, invalid: str) -> datetime:
    if not isinstance(value, str):
        raise TrackerError(missing)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TrackerError(invalid) from None


def _enrollment_override(issue: dict, events: list) -> str | None:
    # A manually curated canonical issue is read-only from the outset.
    # Even changes made *before* the reviewed enrollment timestamp
    # constitute an explicit human override; do not adopt the issue.
    if manually_modified(events, None):
        return "MANUAL_OVERRIDE: historical manual issue edits; no mutation"
    if issue.get("state") == "closed":
        return "MANUAL_OVERRIDE: pre-existing closed issue is human-owned"
    if issue.get("updated_at") != ENROLLMENT_UPDATED_AT:
        return "MANUAL_OVERRIDE: canonical issue changed since reviewed enrollment"
    return None


def _human_comment_after(tracker: dict, comments: list) -> bool:
    # A human comment after enrollment is also an intervention. We must not
    # silently edit a bot status around a human discussion/decision.
    cutoff = _timestamp(tracker.get("created_at"), "tracker creation timestamp unavailable", "invalid tracker creation timestamp")
    for comment in comments:
        if comment is tracker:
            continue
        if not isinstance(comment, dict):
            raise TrackerError("unexpected comment metadata")
        created = _timestamp(comment.get("created_at"), "cannot audit comment timeline", "invalid comment timestamp")
        is_human = (comment.get("user") or {}).get("login") != "github-actions[bot]"
        if created >= cutoff and is_human:
            return True
    return False


def _tracked_override(old: dict, tracker: dict, comments: list, fingerprint: str, human: bool, run_id: int, run_number: int) -> str | None:
    if _human_comment_after(tracker, comments):
        return "MANUAL_OVERRIDE: human discussion after enrollment"
    if old["fingerprint"] != fingerprint:
        return "MANUAL_OVERRIDE: issue title/body/labels changed; no mutation"
    if human:
        return "MANUAL_OVERRIDE: issue manually changed after bot enrollment; no mutation"
    if run_id <= old["run_id"] or run_number <= old["run_number"]:
        return "STALE: already processed or out-of-order run, no mutation"
    return None


def _next_streak(successful: bool, old: dict | None, run_number: int) -> int:
    if not successful:
        return 0
    if old and old["result"] == "GREEN" and run_number == old["run_number"] + 1:
        return min(2, old["green_streak"] + 1)
    return 1


def _changed_while_reconciling(issue_path: str, issue: dict, fingerprint: str, baseline: str) -> bool:
    current = github("GET", issue_path)
    current_events = github("GET", f"{issue_path}/events?per_page=100")
    return (
        not isinstance(current_events, list)
        or len(current_events) == 100
        or current.get("state") != issue.get("state")
        or issue_fingerprint(current) != fingerprint
        or manually_modified(current_events, baseline)
    )


def _write_status(issue_path: str, tracker: dict | None, content: str) -> None:
    if tracker:
        comment_id = tracker.get("id")
        if type(comment_id) is not int or comment_id <= 0:
            raise TrackerError("invalid tracker comment id")
        github("PATCH", f"repos/{REPOSITORY}/issues/comments/{comment_id}", {"body": content})
    else:
        github("POST", f"{issue_path}/comments", {"body": content})


def _unchanged_since(issue_path: str, state: str, fingerprint: str, baseline: str | None) -> bool:
    latest = github("GET", issue_path)
    latest_events = github("GET", f"{issue_path}/events?per_page=100")
    return latest.get("state") == state and issue_fingerprint(latest) == fingerprint and not manually_modified(latest_events, baseline)


def _tracker_comment(comments: list) -> dict | None:
    matching = [c for c in comments if isinstance(c, dict) and str(c.get("body", "")).startswith(MARKER)]
    if len(matching) > 1:
        raise TrackerError("duplicate bot tracker comments")
    return matching[0] if matching else None


def _transition_state(issue_path: str, issue: dict, events: list, fingerprint: str, baseline: str, *, successful: bool, streak: int) -> str | None:
    if issue.get("state") == "open" and streak == 2:
        # Re-read before closing: an intervening human edit blocks any state change.
        if _unchanged_since(issue_path, "open", fingerprint, baseline):
            github("PATCH", issue_path, {"state": "closed", "state_reason": "completed"})
            return "CLOSED: two consecutive successful post-merge runs"
        return "MANUAL_OVERRIDE: state changed before close"
    if issue.get("state") == "closed" and not successful and not manually_modified(events, None):
        if _unchanged_since(issue_path, "closed", fingerprint, None):
            github("PATCH", issue_path, {"state": "open"})
            return "REOPENED: new red master with no human issue edits"
    return None


def reconcile(
    run_id: int,
    sha: str,
    results: dict,
    required: dict | None = None,
    run_number: int | None = None,
) -> str:
    required = required or {"CODEQL": False, "ZAP": False}
    run_number = run_id if run_number is None else run_number
    _validate_run(run_id, sha, results, required, run_number)
    if github("GET", f"repos/{REPOSITORY}/commits/master").get("sha") != sha:
        return "STALE: superseded master SHA, no mutation"
    issue_path = f"repos/{REPOSITORY}/issues/{ISSUE}"
    issue = github("GET", issue_path)
    if issue.get("number") != ISSUE or issue.get("pull_request"):
        raise TrackerError("canonical manually curated issue unavailable")
    fingerprint = issue_fingerprint(issue)
    events = _bounded_list(f"{issue_path}/events?per_page=100", "cannot prove manual issue-event ownership")
    comments = _bounded_list(f"{issue_path}/comments?per_page=100", "cannot uniquely identify tracker comment")
    tracker = _tracker_comment(comments)
    old = parse_comment(tracker) if tracker else None
    human = manually_modified(events, tracker.get("created_at") if old else None)
    if old is None:
        override = _enrollment_override(issue, events)
    else:
        override = _tracked_override(old, tracker, comments, fingerprint, human, run_id, run_number)
    if override:
        return override
    successful = green(results, required)
    if issue.get("state") == "closed" and not successful and manually_modified(events, None):
        return "MANUAL_OVERRIDE: historically human-maintained issue never reopened"
    if issue.get("state") not in ("open", "closed"):
        raise TrackerError("invalid canonical issue state")
    streak = _next_streak(successful, old, run_number)
    state = {
        "fingerprint": fingerprint,
        "run_id": run_id,
        "run_number": run_number,
        "green_streak": streak,
        "sha": sha,
        "result": "GREEN" if successful else "RED",
        "results": results,
        "required": required,
    }
    content = render(state)
    # Check that master did not advance while evaluating the issue.
    if github("GET", f"repos/{REPOSITORY}/commits/master").get("sha") != sha:
        return "STALE: master advanced during reconciliation"
    # Re-check human ownership immediately before any comment mutation.
    # Initial checks are insufficient if a reviewer edits the issue during
    # API pagination or while the security gates finish.
    baseline = tracker.get("created_at") if old else ENROLLMENT_UPDATED_AT
    if _changed_while_reconciling(issue_path, issue, fingerprint, baseline):
        return "MANUAL_OVERRIDE: issue changed while reconciling; no mutation"
    _write_status(issue_path, tracker, content)
    transition = _transition_state(issue_path, issue, events, fingerprint, baseline, successful=successful, streak=streak)
    return transition or f"TRACKED: {'GREEN' if successful else 'RED'}; successes={streak}/2"


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        print("CHECK: single #355, bot-owned status comment, manual edit protection, 2 green runs")
        return 0
    if len(sys.argv) != 2 or sys.argv[1] != "--apply":
        raise TrackerError("expected --check or --apply")
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise TrackerError("repository mismatch")
    results = {name: os.environ.get(f"{name}_RESULT", "") for name in STATUS_KEYS}
    requested = (os.environ.get("REQUIRE_CODEQL"), os.environ.get("REQUIRE_ZAP"))
    if any(value not in ("true", "false") for value in requested):
        raise TrackerError("required scans not resolved")
    message = reconcile(
        int(os.environ.get("GITHUB_RUN_ID", "0")),
        os.environ.get("GITHUB_SHA", ""),
        results,
        {"CODEQL": requested[0] == "true", "ZAP": requested[1] == "true"},
        run_number=int(os.environ.get("GITHUB_RUN_NUMBER", "0")),
    )
    print(message)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TrackerError, ValueError):
        raise SystemExit(
            "REJECTED: master-red tracking refused unsafe or ambiguous state",
        ) from None
