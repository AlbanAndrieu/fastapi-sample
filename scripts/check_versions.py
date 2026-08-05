#!/usr/bin/env python3
"""Fail when Python, npm, and generated runtime versions diverge."""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nabla._release import __version__ as runtime_version  # noqa: E402


def main() -> int:
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        python_version = tomllib.load(pyproject_file)["project"]["version"]
    with (ROOT / "package.json").open(encoding="utf-8") as package_file:
        npm_version = json.load(package_file)["version"]
    with (ROOT / "package-lock.json").open(encoding="utf-8") as lock_file:
        npm_lock_version = json.load(lock_file)["version"]
    with (ROOT / "uv.lock").open("rb") as uv_lock_file:
        uv_packages = tomllib.load(uv_lock_file)["package"]
    uv_version = next(
        package["version"] for package in uv_packages if package["name"] == "fastapi-sample"
    )

    versions = {
        "pyproject.toml": python_version,
        "package.json": npm_version,
        "package-lock.json": npm_lock_version,
        "uv.lock": uv_version,
        "nabla/_release.py": runtime_version,
    }
    if len(set(versions.values())) != 1:
        print(f"Version mismatch: {versions}", file=sys.stderr)
        return 1

    print(f"Versions synchronized: {runtime_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
