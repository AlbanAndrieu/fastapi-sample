"""Reject semantic-release runs when source versions diverge from the latest release."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(
    r"^(?:v)?(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$"
)


def normalize_release_version(value: str) -> str:
    """Normalize a strict stable SemVer tag, accepting the optional conventional v prefix."""
    match = SEMVER_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"release tag must be a stable X.Y.Z version, got {value!r}")
    return match.group("version")


def version_tuple(value: str) -> tuple[int, int, int]:
    """Return a comparable tuple for a normalized stable SemVer version."""
    normalized = normalize_release_version(value)
    major, minor, patch = normalized.split(".")
    return int(major), int(minor), int(patch)


def validate_release_baseline(source_version: str, release_tag: str) -> None:
    """Require checked-in source version to equal the latest published release."""
    normalized_source = normalize_release_version(source_version)
    published_version = normalize_release_version(release_tag)
    if normalized_source == published_version:
        return

    relation = (
        "ahead of"
        if version_tuple(normalized_source) > version_tuple(published_version)
        else "behind"
    )
    raise ValueError(
        "release baseline mismatch: checked-in version "
        f"{normalized_source} is {relation} latest published GitHub Release "
        f"{published_version}. This usually means a release prepare was only partially "
        "published or version files were changed outside semantic-release. Recover the "
        "release baseline before running semantic-release again."
    )


def source_version() -> str:
    """Read the canonical checked-in project version after check_versions.py passed."""
    with (ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    return str(pyproject["project"]["version"])


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_release_baseline.py <latest-github-release-tag>", file=sys.stderr)
        return 2

    current = source_version()
    try:
        validate_release_baseline(current, args[0])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Release baseline synchronized: source={current}, published={args[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
