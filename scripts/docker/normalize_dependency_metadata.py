"""Normalize release-only version metadata before Docker dependency installation."""

from __future__ import annotations

from pathlib import Path
import re
import sys

_NORMALIZED_VERSION = "0.0.0"


def _replace_once(text: str, pattern: str, label: str) -> str:
    updated, count = re.subn(
        pattern,
        rf"\g<1>{_NORMALIZED_VERSION}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(f"expected exactly one {label} version field, found {count}")
    return updated


def normalize_pyproject(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        r'(^name = "fastapi-sample"\nversion = ")[^"]+(")$',
        "project",
    )
    text = _replace_once(
        text,
        r'(^default-version = ")[^"]+(")$',
        "versioningit default",
    )
    text = _replace_once(
        text,
        r'(^\[tool\.commitizen\](?:\n#[^\n]*)*\nversion = ")[^"]+(")',
        "commitizen",
    )
    path.write_text(text, encoding="utf-8")


def normalize_lock(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        r'(^name = "fastapi-sample"\nversion = ")[^"]+(")$',
        "uv.lock project",
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: normalize_dependency_metadata.py PYPROJECT UV_LOCK")
    normalize_pyproject(Path(sys.argv[1]))
    normalize_lock(Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
