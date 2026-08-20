#!/usr/bin/env python3
"""Enforce maintainability limits for modified Python source files.

The gate is intentionally diff/pre-commit oriented: callers pass the Python files
being changed. Existing oversized legacy files therefore do not break unrelated
changes, but modifying one makes the maintainability debt visible immediately.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_WARNING_LINES = 400
DEFAULT_FAILURE_LINES = 700
DEFAULT_EXCLUDES = (
    "**/migrations/**",
    "**/generated/**",
    "**/*_generated.py",
    "**/.venv/**",
    "**/venv/**",
    "docs/site/**",
    "docs/_build/**",
)


def _is_excluded(path: Path, patterns: Iterable[str]) -> bool:
    normalized = path.as_posix().lstrip("./")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as source:
        return sum(1 for _ in source)


def _iter_python_files(paths: Iterable[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        candidates = path.rglob("*.py") if path.is_dir() else (path,)
        for candidate in candidates:
            if candidate.suffix != ".py" or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Python files/directories to inspect")
    parser.add_argument("--warn", type=int, default=DEFAULT_WARNING_LINES)
    parser.add_argument("--fail", type=int, default=DEFAULT_FAILURE_LINES)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional glob pattern to exclude (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.warn < 1 or args.fail <= args.warn:
        raise SystemExit("--fail must be greater than --warn, and both must be positive")

    paths = args.paths or ["nabla", "scripts", "server_app.py"]
    exclusions = (*DEFAULT_EXCLUDES, *args.exclude)
    warnings = 0
    failures = 0

    for path in sorted(_iter_python_files(paths), key=lambda item: item.as_posix()):
        if _is_excluded(path, exclusions):
            continue

        line_count = _line_count(path)
        if line_count > args.fail:
            failures += 1
            print(
                f"ERROR {path}: {line_count} lines exceeds {args.fail}; "
                "refactor before adding significant functionality.",
                file=sys.stderr,
            )
        elif line_count > args.warn:
            warnings += 1
            print(
                f"WARNING {path}: {line_count} lines exceeds {args.warn}; "
                "consider extracting cohesive responsibilities.",
                file=sys.stderr,
            )

    print(f"Code-size gate: {warnings} warning(s), {failures} error(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
