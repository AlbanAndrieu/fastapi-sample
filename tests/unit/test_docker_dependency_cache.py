"""Regression tests for release-version-neutral Docker dependency caching."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = ROOT / "scripts/docker/normalize_dependency_metadata.py"


def _project_lock_version(payload: dict) -> str:
    return next(
        package["version"]
        for package in payload["package"]
        if package["name"] == "fastapi-sample"
    )


def test_dependency_metadata_normalizer_removes_release_only_versions(
    tmp_path: Path,
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    lockfile = tmp_path / "uv.lock"
    shutil.copy2(ROOT / "pyproject.toml", pyproject)
    shutil.copy2(ROOT / "uv.lock", lockfile)

    original_pyproject = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    original_lock = tomllib.loads(lockfile.read_text(encoding="utf-8"))

    subprocess.run(
        [sys.executable, str(NORMALIZER), str(pyproject), str(lockfile)],
        check=True,
    )

    normalized_pyproject = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    normalized_lock = tomllib.loads(lockfile.read_text(encoding="utf-8"))

    assert normalized_pyproject["project"]["version"] == "0.0.0"
    assert normalized_pyproject["tool"]["versioningit"]["default-version"] == "0.0.0"
    assert normalized_pyproject["tool"]["commitizen"]["version"] == "0.0.0"
    assert _project_lock_version(normalized_lock) == "0.0.0"
    assert (
        normalized_pyproject["project"]["dependencies"]
        == original_pyproject["project"]["dependencies"]
    )
    assert len(normalized_lock["package"]) == len(original_lock["package"])


def test_release_image_version_is_injected_without_rewriting_dockerfile() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    semantic_release = (ROOT / ".releaserc.yaml").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "FROM python:3.13-slim-trixie AS dependency-metadata" in dockerfile
    assert "COPY --from=dependency-metadata" in dockerfile
    assert "!scripts/docker/normalize_dependency_metadata.py" in dockerignore
    assert 'ARG APP_VERSION="dev"' in dockerfile
    assert "APP_VERSION=${{ needs.build.outputs.tag }}" in release_workflow
    assert "ARG APP_VERSION" not in semantic_release
    assert '- "Dockerfile"' not in semantic_release
