"""Deployment configuration regression tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


def test_production_smoke_bounds_browser_cost_without_losing_post_deploy_ui_check() -> None:
    smoke = (ROOT / ".github/workflows/production-smoke.yml").read_text(encoding="utf-8")

    assert "pull_request:" in smoke
    assert "workflow_dispatch:" in smoke
    assert "workflow_call:" in smoke
    assert smoke.count("if: github.event_name != 'pull_request'") == 3
    assert "npx --no-install playwright install --with-deps --only-shell chromium" in smoke
    assert "npx playwright install --with-deps chromium" not in smoke
    assert "--omit=dev" in smoke
    assert "timeout-minutes: 6" in smoke
    assert "--retry-all-errors" in smoke
    assert "--connect-timeout 10" in smoke
    assert "--max-time 30" in smoke
    assert "fetch-depth: 0" not in smoke
    assert "EXPECTED_VERSION=\"${expected}\" node scripts/check-production-api-ui.mjs" in smoke


def test_semantic_release_uses_normal_post_recovery_flow() -> None:
    workflow = (ROOT / ".github/workflows/semantic-release.yml").read_text(encoding="utf-8")

    assert "python scripts/check_release_baseline.py" in workflow
    assert "npx semantic-release" in workflow
    assert "semantic-release-published" in workflow
    assert "git tag --force 1.4.0" not in workflow
    assert "RECOVERY_VERSION" not in workflow
    assert "scripts/set_release_version.py" not in workflow
    assert "npm version" not in workflow
    assert "npm pkg delete" not in workflow
    assert "@semantic-release/gitlab" not in workflow


def test_recovery_manifest_and_changelog_document_1_4_1() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    manifest = (ROOT / "docs/release-1.4.1.md").read_text(encoding="utf-8")

    assert "## 1.4.1 — homelab diagnostics and release recovery" in changelog
    assert "does **not** force-move" in manifest
    assert "would clobber existing tag" in manifest


def test_package_publication_respects_private_classifier_and_least_privilege() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "semantic-release-published" in workflow
    assert "\n  build:\n" in workflow
    assert "\n  publish_github:\n" in workflow
    assert "\n  publish_testpypi:\n" in workflow
    assert "\n  publish_pypi:\n" in workflow
    assert '[[ ! "${release_tag}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in workflow
    assert "ref: ${{ steps.release_ref.outputs.tag }}" in workflow
    assert "environment: testpypi" not in workflow
    assert "environment: pypi" not in workflow
    assert workflow.count("id-token: write") == 2
    assert workflow.count("pypa/gh-action-pypi-publish@") == 2
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert workflow.count(
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
    ) == 3
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "skip-existing: true" in workflow
    assert "repository_url:" not in workflow
    assert "skip_existing:" not in workflow
    assert "GITHUB_ENV" not in workflow


def test_dockerfile_hadolint_hardening_is_explicit() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "# hadolint ignore=DL3008" in dockerfile
    assert "USER 999:999" in dockerfile
    assert "USER jm-python" not in dockerfile
    assert (
        'CMD ["curl", "--fail", "--silent", "--show-error", '
        '"http://localhost:8080/health"]'
    ) in dockerfile
    assert "CMD curl --fail" not in dockerfile
