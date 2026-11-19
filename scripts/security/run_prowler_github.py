#!/usr/bin/env python3
"""Private, manually authorized Prowler GitHub posture for fastapi-sample only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from import_defectdojo import MAX_REPORT_BYTES, validate_prowler

ROOT = Path(__file__).resolve().parents[2]
REPO = "AlbanAndrieu/fastapi-sample"
FILENAME = "prowler-github"


def master_revision() -> str:
    def git(ref: str) -> str:
        return subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()

    revision = git("HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None or revision != git("refs/remotes/origin/master"):
        raise RuntimeError("Prowler requires HEAD equal to fetched origin/master")
    return revision


def scan(out: Path, revision: str) -> int:
    tool = shutil.which("prowler")
    if not tool:
        raise RuntimeError("Prowler 5.50.0 must be installed locally")
    token = os.environ.get("PROWLER_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("dedicated read-only Prowler token missing")
    env = os.environ.copy()
    for name in ("GITHUB_APP_ID", "GITHUB_APP_KEY", "GITHUB_OAUTH_APP_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "PROWLER_GITHUB_TOKEN"):
        env.pop(name, None)
    env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
    version = subprocess.run(
        [tool, "--version"], capture_output=True, text=True, timeout=15, check=False, env=env,
    )
    if version.returncode or not re.search(r"(?<![0-9.])5[.]50[.]0(?![0-9.])", version.stdout + version.stderr):
        raise RuntimeError("unexpected Prowler version")
    result = subprocess.run(
        [tool, "github", "--repository", REPO, "--output-formats", "json-ocsf",
         "--output-directory", str(out), "--output-filename", FILENAME],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=900,
        check=False,
    )
    if result.returncode not in (0, 3):
        raise RuntimeError("Prowler technical scan failure; private evidence not approved")
    files = list(out.glob(FILENAME + "*.json"))
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise RuntimeError("missing or ambiguous native Prowler report")
    source = files[0]
    with source.open("rb") as stream:
        content = stream.read(MAX_REPORT_BYTES + 1)
    if not 0 < len(content) <= MAX_REPORT_BYTES:
        raise RuntimeError("Prowler report outside allowed size")
    failed = validate_prowler(content)
    if result.returncode == 3 and not failed:
        raise RuntimeError("inconsistent Prowler findings verdict")
    target = out / (FILENAME + ".json")
    if source != target:
        source.rename(target)
    target.chmod(0o600)
    if master_revision() != revision:
        raise RuntimeError("master reference changed during scan")
    receipt = {
        "schema_version": 1,
        "project": "fastapi-sample",
        "mode": "master",
        "state": "complete",
        "policy_status": "needs_review" if failed else "pass",
        "critical_count": 0,
        "prowler_failed_count": failed,
        "revision": revision,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "reports": {target.name: hashlib.sha256(content).hexdigest()},
    }
    (out / "scan-receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Prowler collected: checks requiring triage={failed}")
    return 3 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        parser.error("Prowler posture pilot is LAN/workstation only")
    os.umask(0o077)
    out = args.output_dir.absolute()
    if out.is_symlink() or out.resolve().is_relative_to(ROOT):
        parser.error("Prowler output must be outside the checkout")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out.stat().st_uid != os.geteuid() or out.stat().st_mode & 0o077 or any(out.iterdir()):
        parser.error("Prowler output directory must be private and empty")
    try:
        return scan(out, master_revision())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("Prowler scan refused or incomplete; no approved receipt")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
