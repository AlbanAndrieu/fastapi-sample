"""Deployment configuration regression tests."""

import json
from pathlib import Path

import pytest

from scripts import set_release_version as release_version

ROOT = Path(__file__).resolve().parents[2]


def _write_release_version_fixture(root: Path, *, valid_dockerfile: bool = True) -> list[Path]:
    """Create the minimal release metadata set consumed by the sync script."""
    (root / "nabla").mkdir()
    files = {
        root / "pyproject.toml": (
            '[project]\nname = "fastapi-sample"\nversion = "1.4.0"\n\n'
            '[tool.versioningit]\ndefault-version = "1.4.0"\n\n'
            '[tool.commitizen]\nversion = "1.4.0"\n'
        ),
        root / "nabla/_release.py": '__version__ = "1.4.0"\n',
        root / "uv.lock": '[[package]]\nname = "fastapi-sample"\nversion = "1.4.0"\n',
        root / "Dockerfile": (
            'ARG APP_VERSION="1.4.0"\n' if valid_dockerfile else "FROM python:3.13\n"
        ),
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    return list(files)


def test_vercel_is_a_lightweight_fastapi_cloud_proxy() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] is None
    assert config["git"]["deploymentEnabled"] == {"*": False, "master": True}
    assert config["ignoreCommand"] == '[ "$VERCEL_GIT_COMMIT_REF" != "master" ]'
    assert config["rewrites"] == [
        {
            "source": "/:path*",
            "destination": "https://fastapi-sample.fastapicloud.dev/:path*",
        }
    ]

    ignored = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert "!pyproject.toml" not in ignored
    assert "!uv.lock" not in ignored
    assert "!nabla" not in ignored


def test_production_branch_and_release_branch_are_master() -> None:
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    semantic_release = (ROOT / ".github/workflows/semantic-release.yml").read_text(
        encoding="utf-8"
    )
    release = (ROOT / ".releaserc.yaml").read_text(encoding="utf-8")

    assert "branches: [master]" in python_ci
    assert "branches: [master]" in codeql
    assert "branches: [master]" in semantic_release
    assert "\n  - master\n" in release
    assert "branches: [main]" not in semantic_release
    assert "\n  - main\n" not in release


def test_production_validation_provides_required_auth_settings() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")

    required_test_settings = (
        "KEYCLOAK_CLIENT_ID: test",
        "KEYCLOAK_CLIENT_SECRET: test-secret",
        "KEYCLOAK_REALM: test",
        "KEYCLOAK_SERVER_URL: http://localhost:8080",
        "OAUTH_TOKEN_SECRET: mocked-oauth-token-secret",
    )
    for setting in required_test_settings:
        assert setting in deploy
        assert setting in python_ci


def test_fastapi_cloud_deploy_uses_project_cli() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "run: uv run fastapi deploy" in deploy
    assert "uvx fastapi-cloud-cli" not in deploy


def test_fastapi_cloud_deploy_job_sets_up_python() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    deploy_job = deploy.split("\n  deploy:\n", maxsplit=1)[1]

    assert 'PYTHON_VERSION: "3.13"' in deploy_job
    assert "- name: Set up Python" in deploy_job
    assert "python-version: ${{ env.PYTHON_VERSION }}" in deploy_job


def test_release_dispatch_deploys_immutable_tag_then_runs_smoke() -> None:
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    smoke = (ROOT / ".github/workflows/production-smoke.yml").read_text(encoding="utf-8")

    assert "types: [semantic-release-published]" in deploy
    assert "branches: [master]" not in deploy
    assert deploy.count("ref: ${{ github.event.client_payload.tag || github.sha }}") == 2
    assert "uses: ./.github/workflows/production-smoke.yml" in deploy
    assert "workflow_call:" in smoke
    assert "workflow_run:" not in smoke
    assert "GITHUB_ENV" not in smoke


def test_semantic_release_recovers_exactly_1_4_1_then_dispatches_deploy() -> None:
    workflow = (ROOT / ".github/workflows/semantic-release.yml").read_text(encoding="utf-8")

    assert 'SOURCE_VERSION_BEFORE}" == "1.4.0"' in workflow
    assert 'LATEST_RELEASE_TAG}" == "1.4.0"' in workflow
    assert 'RECOVERY_VERSION="1.4.1"' in workflow
    assert 'python scripts/set_release_version.py "${RECOVERY_VERSION}"' in workflow
    assert 'npm version "${RECOVERY_VERSION}" --no-git-tag-version --ignore-scripts' in workflow
    assert "git tag --force 1.4.0" not in workflow
    assert 'SOURCE_VERSION_BEFORE}" == "1.4.1"' in workflow
    assert 'REMOTE_TAG_SHA}" != "${HEAD_SHA}"' in workflow
    assert "semantic-release-published" in workflow


def test_release_version_sync_updates_all_non_npm_sources(tmp_path, monkeypatch) -> None:
    paths = _write_release_version_fixture(tmp_path)
    monkeypatch.setattr(release_version, "ROOT", tmp_path)

    release_version.set_release_version("1.4.1")

    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "1.4.1" in content
        assert "1.4.0" not in content


def test_release_version_sync_is_transactional_on_drift(tmp_path, monkeypatch) -> None:
    paths = _write_release_version_fixture(tmp_path, valid_dockerfile=False)
    before = {path: path.read_text(encoding="utf-8") for path in paths}
    monkeypatch.setattr(release_version, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="Dockerfile: expected exactly one version match"):
        release_version.set_release_version("1.4.1")

    assert {path: path.read_text(encoding="utf-8") for path in paths} == before


def test_recovery_manifest_and_changelog_document_1_4_1() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    manifest = (ROOT / "docs/release-1.4.1.md").read_text(encoding="utf-8")

    assert "## 1.4.1 — homelab diagnostics and release recovery" in changelog
    assert "does **not** force-move" in manifest
    assert "scripts/set_release_version.py" in manifest
    assert "would clobber existing tag" in manifest


def test_package_publication_uses_single_validated_release_dispatch() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "semantic-release-published" in workflow
    assert "\n  release:\n" not in workflow
    assert '[[ ! "${release_tag}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in workflow
    assert "ref: ${{ steps.release_ref.outputs.tag }}" in workflow
    assert "GITHUB_ENV" not in workflow
