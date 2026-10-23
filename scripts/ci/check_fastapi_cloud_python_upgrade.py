#!/usr/bin/env python3
"""Audit Cloud Python upgrades without mutating the deployable project.

The platform supports maintained CPython versions, but a successful Cloud
deployment also requires resolving the entire native-heavy uv dependency graph.
The current lock covers 3.13 only; never edit uv.lock by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ("3.14.9", "3.15.1")
REQUIREMENT = re.compile(r'(?m)^requires-python\s*=\s*"==3\.13\.\*"\s*$')


def audit(root: Path, candidate: str) -> dict[str, object]:
    """Read both manifests; report readiness, not a guessed compatibility pass."""
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    locked = (root / "uv.lock").read_text(encoding="utf-8")
    project_data = tomllib.loads(project)
    lock_data = tomllib.loads(locked)
    required = project_data["project"]["requires-python"]
    locked_python = lock_data["requires-python"]
    if not REQUIREMENT.search(project) or required != "==3.13.*":
        raise ValueError("project Python constraint changed; review the migration gate")
    if locked_python != required:
        raise ValueError("uv.lock and pyproject.toml disagree")
    packages = lock_data.get("package", [])
    native_wheels = [
        str(package["name"])
        for package in packages
        if any(
            "cp313" in str(wheel.get("url", ""))
            for wheel in package.get("wheels", [])
        )
    ]
    if not (root / ".python-version").read_text(encoding="utf-8").strip().startswith("3.13."):
        raise ValueError(".python-version is not the approved 3.13 runtime")
    return {
        "status": "BLOCKED_PENDING_RESOLUTION",
        "candidate": candidate,
        "current_requires_python": required,
        "locked_requires_python": locked_python,
        "lock_packages": len(packages),
        "packages_with_cp313_wheels": len(native_wheels),
        "representative_native_packages": native_wheels[:12],
        "next_steps": [
            "re-resolve uv.lock on the candidate interpreter",
            "install production groups with --no-default-groups",
            "run unit and integration tests including native dependencies",
            "smoke-test Docker/Talos and external FastAPI Cloud before cutover",
        ],
    }


def probe(root: Path, candidate: str, allow_network: bool) -> dict[str, object]:
    """Use a disposable copy, uv --dry-run, and never install in production."""
    uv = shutil.which("uv")
    if uv is None:
        return {"status": "NOT_RUN", "reason": "uv executable unavailable"}
    with tempfile.TemporaryDirectory(prefix="nabla-python-cloud-upgrade-") as temp:
        stage = Path(temp)
        raw = (root / "pyproject.toml").read_text(encoding="utf-8")
        version = ".".join(candidate.split(".")[:2])
        edited, count = REQUIREMENT.subn(f'requires-python = "=={version}.*"', raw, count=1)
        if count != 1:
            raise ValueError("cannot safely prepare candidate project constraint")
        (stage / "pyproject.toml").write_text(edited, encoding="utf-8")
        (stage / "uv.lock").write_bytes((root / "uv.lock").read_bytes())
        (stage / ".python-version").write_text(candidate + "\n", encoding="utf-8")
        for filename in ("README.md", "LICENSE"):
            source = root / filename
            if source.is_file():
                shutil.copyfile(source, stage / filename)
        env = {**os.environ, "UV_PYTHON_DOWNLOADS": "never"}
        if not allow_network:
            env["UV_OFFLINE"] = "1"
        try:
            result = subprocess.run(
                [uv, "lock", "--dry-run"],
                cwd=stage,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"status": "NOT_RUN", "reason": "candidate resolution timed out"}
        return {
            "status": "RESOLVER_PASSED_NOT_DEPLOYABLE" if result.returncode == 0 else "RESOLVER_FAILED",
            "candidate": candidate,
            "offline": not allow_network,
            "exit_code": result.returncode,
            "diagnostic_tail": (result.stderr or result.stdout)[-1200:],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=CANDIDATES, default="3.14.9")
    parser.add_argument("--probe", action="store_true", help="dry-run lock in disposable directory")
    parser.add_argument("--allow-network", action="store_true", help="permit uv to resolve PyPI/Git metadata")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.allow_network and not args.probe:
        parser.error("--allow-network requires --probe")
    try:
        result = audit(args.root, args.candidate)
        if args.probe:
            result["probe"] = probe(args.root, args.candidate, args.allow_network)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.exit(2, f"PYTHON_UPGRADE_AUDIT_ERROR: {type(exc).__name__}: {exc}\n")
    return 0 if not args.probe or result["probe"]["status"] == "RESOLVER_PASSED_NOT_DEPLOYABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
