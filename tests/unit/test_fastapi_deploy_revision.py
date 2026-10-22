"""Offline source-attestation regression tests for token-only deployment."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "stamp_fastapi_deploy_revision.py"
_SPEC = importlib.util.spec_from_file_location("stamp_fastapi_deploy_revision", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_stamps_full_immutable_sha_and_remains_valid_python(tmp_path: Path) -> None:
    target = tmp_path / "_deployment_revision.py"
    target.write_text('DEPLOYED_BUILD_SHA = ""\n', encoding="utf-8")
    _MODULE.stamp_revision("a" * 40, target=target)
    namespace: dict[str, object] = {}
    exec(compile(target.read_text(), str(target), "exec"), namespace)
    assert namespace["DEPLOYED_BUILD_SHA"] == "a" * 40


@pytest.mark.parametrize(
    "sha",
    ["", "a" * 39, "a" * 41, "F" * 40, "git branch --show-current", "a" * 40 + "\n"],
)
def test_rejects_untrusted_or_abbreviated_revision(sha: str, tmp_path: Path) -> None:
    target = tmp_path / "_deployment_revision.py"
    target.write_text('DEPLOYED_BUILD_SHA = ""\n', encoding="utf-8")
    with pytest.raises(ValueError, match="40-character Git SHA"):
        _MODULE.stamp_revision(sha, target=target)
    assert target.read_text() == 'DEPLOYED_BUILD_SHA = ""\n'


def test_missing_tracked_revision_module_is_not_created(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _MODULE.stamp_revision("a" * 40, target=tmp_path / "missing.py")


def test_unstamped_source_checkout_claims_no_deployed_sha() -> None:
    from nabla._deployment_revision import DEPLOYED_BUILD_SHA

    assert DEPLOYED_BUILD_SHA == ""


def test_source_revision_takes_priority_over_stale_cloud_environment(monkeypatch) -> None:
    from nabla import version

    monkeypatch.setenv("BUILD_REVISION", "b" * 40)
    monkeypatch.setattr(version, "DEPLOYED_BUILD_SHA", "a" * 40)
    assert version.resolve_build_revision() == "a" * 40
    monkeypatch.setattr(version, "DEPLOYED_BUILD_SHA", "")
    assert version.resolve_build_revision() == "b" * 40
    monkeypatch.delenv("BUILD_REVISION")
    monkeypatch.setenv("GIT_SHA", "c" * 40)
    assert version.resolve_build_revision() == "c" * 40
