"""Tests for the semantic-release published-version baseline guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_release_baseline.py"
SPEC = importlib.util.spec_from_file_location("check_release_baseline", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

normalize_release_version = MODULE.normalize_release_version
validate_release_baseline = MODULE.validate_release_baseline


def test_release_baseline_accepts_equal_version() -> None:
    validate_release_baseline("1.5.1", "1.5.1")
    validate_release_baseline("1.5.1", "v1.5.1")


def test_release_baseline_rejects_partial_prepare_ahead_of_release() -> None:
    with pytest.raises(ValueError, match="ahead of latest published GitHub Release"):
        validate_release_baseline("1.6.0", "1.5.1")


def test_release_baseline_rejects_sources_behind_release() -> None:
    with pytest.raises(ValueError, match="behind latest published GitHub Release"):
        validate_release_baseline("1.5.0", "1.5.1")


@pytest.mark.parametrize("value", ["", "1.5", "1.5.1-rc.1", "release-1.5.1"])
def test_release_baseline_rejects_non_stable_semver(value: str) -> None:
    with pytest.raises(ValueError, match="stable X.Y.Z"):
        normalize_release_version(value)
