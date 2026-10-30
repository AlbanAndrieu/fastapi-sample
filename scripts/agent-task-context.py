"""Bounded, offline FastAPI agent context and test router.

Read-only. No remote fetch, dependency installation, CI, secret inspection,
or runtime calls. Output describes evidence to collect, never test success.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("auto", "ui", "cloud", "truenas", "metrics", "api", "quality")
CHECKS = {
    "ui": "just ui-quick",
    "cloud": "just ui-quick",
    "truenas": "just test-runtime-evidence",
    "metrics": "bash scripts/run-pytest-compact.sh tests/unit/test_platform_metrics.py",
    "api": "just offline-l1",
    "quality": "just test-local-first",
}
SKILLS = {
    "ui": ["local-first-quality"],
    "cloud": ["local-first-quality", "fastapi-cloud"],
    "truenas": ["local-first-quality", "homelab-runtime-status"],
    "metrics": ["local-first-quality", "homelab-service-contract"],
    "api": ["local-first-quality", "fastapi"],
    "quality": ["local-first-quality"],
}
DEFAULT_MAX_PATHS = 24


def git(*arguments: str) -> tuple[bool, str]:
    try:
        command = subprocess.run(
            ["git", *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=6, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return command.returncode == 0, command.stdout.strip()


def base_ref() -> tuple[str, str]:
    requested = os.environ.get("QUALITY_BASE_REF")
    candidates = [requested] if requested else ["origin/master", "master"]
    for candidate in candidates:
        if not candidate:
            continue
        exists, _ = git("rev-parse", "--verify", candidate + "^{commit}")
        if exists:
            reachable, _ = git("merge-base", candidate, "HEAD")
            return candidate, "AVAILABLE" if reachable else "DIVERGED"
    return "none", "NOT_RUN"


def changed_paths(base: str, base_state: str) -> list[str]:
    paths: set[str] = set()
    if base_state == "AVAILABLE":
        ok, output = git("diff", "--name-only", base + "...HEAD")
        if ok:
            paths.update(output.splitlines())
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        ok, output = git(*args)
        if ok:
            paths.update(output.splitlines())
    return sorted(path for path in paths if path)


def inferred_task(paths: list[str]) -> str:
    if any(path.startswith("nabla/api/assets/") or path.startswith("tests/js/")
           for path in paths):
        return "ui"
    if any("cloud" in path and path.startswith(("scripts/", "nabla/", "tests/"))
           for path in paths):
        return "cloud"
    if any("platform_metrics" in path or "prometheus" in path or "metrics-auth" in path
           for path in paths):
        return "metrics"
    if any("truenas" in path or "homelab" in path for path in paths):
        return "truenas"
    if any(path.startswith(("nabla/", "tests/")) for path in paths):
        return "api"
    return "quality"


def context(task: str, limit: int) -> dict[str, object]:
    valid_repo, _ = git("rev-parse", "--is-inside-work-tree")
    if not valid_repo:
        return {"state": "NOT_RUN", "reason": "git_checkout_unavailable"}
    _, branch = git("branch", "--show-current")
    _, sha = git("rev-parse", "HEAD")
    base, base_state = base_ref()
    paths = changed_paths(base, base_state)
    selected = inferred_task(paths) if task == "auto" else task
    return {
        "schema": "fastapi-agent-context/v1",
        "branch": branch or "detached",
        "head": sha if len(sha) == 40 else "unknown",
        "base": base,
        "baseState": base_state,
        "prState": "NOT_CHECKED",
        "task": selected,
        "changedCount": len(paths),
        "changedPaths": paths[:limit],
        "omittedPaths": max(0, len(paths) - limit),
        "skills": SKILLS[selected],
        "firstCheck": CHECKS[selected],
        "localGate": "NOT_RUN",
        "runtime": "NOT_RUN",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=TASKS, default="auto")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    raw_limit = os.environ.get("AGENT_CONTEXT_MAX_PATHS", str(DEFAULT_MAX_PATHS))
    if not raw_limit.isdecimal() or not 1 <= int(raw_limit) <= 100:
        parser.error("AGENT_CONTEXT_MAX_PATHS must be 1..100")
    report = context(args.task, int(raw_limit))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    elif report.get("state") == "NOT_RUN":
        print("Agent context: NOT_RUN (Git checkout unavailable)")
    else:
        print(f"HEAD {report['head']} | branch {report['branch']} | base {report['baseState']}")
        print(f"Task {report['task']} | changed {report['changedCount']} (show {len(report['changedPaths'])})")
        for path in report["changedPaths"]:
            print("  " + path)
        if report["omittedPaths"]:
            print(f"  ... {report['omittedPaths']} other paths")
        print("Skills: " + ", ".join(report["skills"]))
        print("First check: " + report["firstCheck"])
        print("PR/L3/runtime: NOT_CHECKED / NOT_RUN / NOT_RUN")
    return 0 if report.get("state") != "NOT_RUN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
