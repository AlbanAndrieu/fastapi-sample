"""Deployment configuration regression tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vercel_is_a_lightweight_fastapi_cloud_proxy() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] is None
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

    assert 'SOURCE_VERSION}" == "1.4.0"' in workflow
    assert 'LATEST_RELEASE_TAG}" == "1.4.0"' in workflow
    assert 'RELEASE_TAG}" != "1.4.1"' in workflow
    assert "semantic-release-published" in workflow


def test_package_publication_uses_single_validated_release_dispatch() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "semantic-release-published" in workflow
    assert "\n  release:\n" not in workflow
    assert '[[ ! "${release_tag}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in workflow
    assert "ref: ${{ steps.release_ref.outputs.tag }}" in workflow
    assert "GITHUB_ENV" not in workflow
