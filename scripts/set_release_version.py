#!/usr/bin/env python3
"""Synchronize non-npm release version files to an explicit stable SemVer."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_STABLE_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

Replacement = tuple[str, str]


def _render_replacements(path: Path, replacements: Iterable[Replacement]) -> str:
    """Validate every exact-one replacement for one file before returning content."""
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT)
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"{relative}: expected exactly one version match, found {count}")
    return text


def set_release_version(version: str) -> None:
    """Synchronize every non-npm version source without partial writes on failure."""
    if _STABLE_SEMVER.fullmatch(version) is None:
        raise ValueError(f"expected stable SemVer X.Y.Z, got {version!r}")

    replacements: dict[Path, tuple[Replacement, ...]] = {
        ROOT / "pyproject.toml": (
            (
                r'(?<=name = "fastapi-sample"\n)version = "[0-9]+\.[0-9]+\.[0-9]+"',
                f'version = "{version}"',
            ),
            (
                r'(?<=\[tool\.versioningit\]\n)default-version = "[0-9]+\.[0-9]+\.[0-9]+"',
                f'default-version = "{version}"',
            ),
            (
                r'(\[tool\.commitizen\](?:\n#[^\n]*)*\n)version = "[0-9]+\.[0-9]+\.[0-9]+"',
                rf'\g<1>version = "{version}"',
            ),
        ),
        ROOT / "nabla/_release.py": (
            (
                r'^__version__ = "[0-9]+\.[0-9]+\.[0-9]+"$',
                f'__version__ = "{version}"',
            ),
        ),
        ROOT / "uv.lock": (
            (
                r'(?<=name = "fastapi-sample"\n)version = "[0-9]+\.[0-9]+\.[0-9]+"',
                f'version = "{version}"',
            ),
        ),
        ROOT / "Dockerfile": (
            (
                r'^ARG APP_VERSION="[0-9]+\.[0-9]+\.[0-9]+"$',
                f'ARG APP_VERSION="{version}"',
            ),
        ),
    }

    rendered = {
        path: _render_replacements(path, file_replacements)
        for path, file_replacements in replacements.items()
    }
    for path, text in rendered.items():
        path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="stable SemVer release version, for example 1.5.8")
    args = parser.parse_args()

    try:
        set_release_version(args.version)
    except (OSError, ValueError) as exc:
        print(f"Release version synchronization failed: {exc}", file=sys.stderr)
        return 1

    print(f"Synchronized non-npm release version files: {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
