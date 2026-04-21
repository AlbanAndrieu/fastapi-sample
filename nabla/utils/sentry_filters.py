"""Helpers for filtering Sentry setup in non-production contexts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import sys
from typing import Optional


def _argv_contains_pytest(argv: Sequence[str]) -> bool:
    """Return ``True`` when process arguments indicate a pytest execution."""
    for arg in argv:
        name = Path(arg).name.lower()
        if name.startswith("pytest") or "pytest" in arg.lower():
            return True
    return False


def is_pytest_process(
    *,
    argv: Optional[Sequence[str]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return ``True`` when running from pytest."""
    current_env = os.environ if env is None else env
    if "PYTEST_CURRENT_TEST" in current_env or "PYTEST_VERSION" in current_env:
        return True
    current_argv = sys.argv if argv is None else argv
    return _argv_contains_pytest(current_argv)


def should_initialize_sentry() -> bool:
    """Return whether Sentry should be initialized in this process."""
    return not is_pytest_process()
