"""Dependency-free guard against GitHub-hosted runner allocation for Draft PRs.

This is a conservative L1 contract, not a substitute for actionlint/zizmor.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = re.compile(r"github\.event\.pull_request\.draft\s*==\s*false")
TRIGGER = re.compile(r"^  pull_request:\s*$", re.MULTILINE)
REVIEW = re.compile(r"\bready_for_review\b")
JOBS = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


def workflow_jobs(source: str) -> list[tuple[str, str]]:
    """Extract job declarations and their pre-step headers, preserving if blocks."""
    lines = source.splitlines()
    try:
        start = lines.index("jobs:")
    except ValueError as exc:
        raise ValueError("missing jobs block") from exc
    result: list[tuple[str, str]] = []
    name: str | None = None
    header: list[str] = []
    for line in lines[start + 1 :]:
        match = JOBS.fullmatch(line)
        if match:
            if name is not None:
                result.append((name, "\n".join(header)))
            name, header = match.group(1), []
            continue
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        if name is not None and not line.startswith("    steps:"):
            header.append(line)
    if name is not None:
        result.append((name, "\n".join(header)))
    return result


def check_workflows(directory: Path) -> tuple[int, int, list[str]]:
    """Require a review event and draft guard on every pull-request job."""
    failures: list[str] = []
    workflows = 0
    jobs_checked = 0
    for path in sorted((*directory.glob("*.yml"), *directory.glob("*.yaml"))):
        text = path.read_text(encoding="utf-8")
        triggers = text.split("\njobs:", 1)[0]
        if not TRIGGER.search(triggers):
            continue
        workflows += 1
        if not REVIEW.search(triggers):
            failures.append(f"{path.name}: missing ready_for_review trigger")
        try:
            jobs = workflow_jobs(text)
        except ValueError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        if not jobs:
            failures.append(f"{path.name}: missing jobs")
        for name, header in jobs:
            jobs_checked += 1
            if not re.search(r"^    (?:runs-on|uses):", header, re.MULTILINE):
                failures.append(f"{path.name}:{name}: missing runner/reusable workflow")
            if not GUARD.search(header) or not re.search(r"^    if:", header, re.MULTILINE):
                failures.append(f"{path.name}:{name}: missing draft PR guard")
    if workflows == 0:
        failures.append("no pull_request workflows found")
    return workflows, jobs_checked, failures


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: python scripts/ci/check_draft_workflows.py [REPO_ROOT]", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT
    count, jobs, failures = check_workflows(root / ".github" / "workflows")
    if failures:
        for failure in failures:
            print(f"DRAFT_GUARD_FAIL {failure}", file=sys.stderr)
        return 1
    print(f"DRAFT_GUARD_OK workflows={count} jobs={jobs} github_minutes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
