#!/usr/bin/env python3
"""Read-only account Actions usage inventory (requires gh auth login).
Usage: python3 scripts/github-actions-usage.py --days 30 [--owner AlbanAndrieu]
Reports wall-clock job minutes (not invoiced runner-weighted minutes),
artifact bytes, and workflow totals; no tokens, secrets or files uploaded.
"""

import argparse
import collections
import datetime as dt
import json
import subprocess
import sys

UTC = dt.timezone.utc


def api(path):
    p = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True, check=True)
    pages = json.loads(p.stdout)
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        return pages
    if isinstance(pages, list):
        return [entry for page in pages for entry in (page if isinstance(page, list) else [page])]
    return [pages]


def items(path, key):
    # GitHub paginates envelope responses; each page has a nested list.
    return [row for page in api(path) for row in page.get(key, [])]


def timeval(raw):
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None


def add_run_jobs(name, run, row):
    row["runs"] += 1
    for job in items(f"repos/{name}/actions/runs/{run['id']}/jobs?per_page=100", "jobs"):
        if job.get("conclusion") == "skipped":
            row["skipped_jobs"] += 1
        start, end = timeval(job.get("started_at")), timeval(job.get("completed_at"))
        if start and end:
            row["job_wall_minutes"] += max(0, (end - start).total_seconds() / 60)


def collect_repo(name, since, max_runs, total):
    runs = items(f"repos/{name}/actions/runs?per_page=100&created=%3E%3D{since.date().isoformat()}", "workflow_runs")
    for artifact in items(f"repos/{name}/actions/artifacts?per_page=100", "artifacts"):
        if not artifact.get("expired"):
            total[f"{name} :: stored artifacts"]["artifact_mib"] += artifact.get("size_in_bytes", 0) / 1048576
    for run in runs[:max_runs]:
        add_run_jobs(name, run, total[f"{name} :: {run.get('name') or run.get('path') or 'unknown'}"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner", default="AlbanAndrieu")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--max-runs", type=int, default=40)
    p.add_argument("--repo", action="append", help="Repository name; repeat to include more. Defaults to the four active projects.")
    a = p.parse_args()
    since = dt.datetime.now(UTC) - dt.timedelta(days=a.days)
    selected = a.repo or ["nabla-compose", "fastapi-sample", "nabla-site-alban", "nabla-site-bababou"]
    total = collections.defaultdict(lambda: {"runs": 0, "job_wall_minutes": 0.0, "artifact_mib": 0.0, "skipped_jobs": 0})
    for repo in selected:
        name = f"{a.owner}/{repo}"
        try:
            collect_repo(name, since, a.max_runs, total)
        except subprocess.CalledProcessError as exc:
            print(f"WARNING: {name}: API unavailable ({exc.returncode})", file=sys.stderr)
    print("repo / workflow\truns\tjob wall min\tstored MiB\tskipped jobs")
    for key, d in sorted(total.items(), key=lambda x: -(x[1]["job_wall_minutes"] + x[1]["artifact_mib"])):
        print(f"{key}\t{d['runs']}\t{d['job_wall_minutes']:.1f}\t{d['artifact_mib']:.1f}\t{d['skipped_jobs']}")
    print("Note: wall minutes are NOT GitHub billed minutes. See Billing > Usage for authoritative credits.", file=sys.stderr)


if __name__ == "__main__":
    main()
