"""Deployment configuration regression tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vercel_is_a_lightweight_fastapi_cloud_proxy() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["framework"] is None
    assert config["git"]["deploymentEnabled"] is False
    assert config["github"]["enabled"] is False
    assert "ignoreCommand" not in config
    assert config["rewrites"] == [
        {
            "source": "/:path*",
            "destination": "https://fastapi-sample.fastapicloud.dev/:path*",
        },
    ]

    ignored = (ROOT / ".vercelignore").read_text(encoding="utf-8")
    assert "!pyproject.toml" not in ignored
    assert "!uv.lock" not in ignored
    assert "!nabla" not in ignored


def test_production_branch_and_release_branch_are_master() -> None:
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    semantic_release = (ROOT / ".github/workflows/semantic-release.yml").read_text(
        encoding="utf-8",
    )
    release = (ROOT / ".releaserc.yaml").read_text(encoding="utf-8")

    assert "branches: [master]" in python_ci
    assert "branches: [master]" in codeql
    assert "branches: [master]" in semantic_release
    assert "\n  - master\n" in release
    assert "branches: [main]" not in semantic_release
    assert "\n  - main\n" not in release


def test_python_ci_provides_required_auth_settings() -> None:
    """CI retains its tests, but no longer deploys the application."""
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    required_test_settings = (
        "KEYCLOAK_CLIENT_ID: test",
        "KEYCLOAK_CLIENT_SECRET: test-secret",
        "KEYCLOAK_REALM: test",
        "KEYCLOAK_SERVER_URL: http://localhost:8080",
        "OAUTH_TOKEN_SECRET: mocked-oauth-token-secret",
    )
    assert all(setting in python_ci for setting in required_test_settings)


def test_github_workflows_never_deploy_or_mutate_fastapi_cloud() -> None:
    """FastAPI Cloud deploys independently of GitHub Actions."""
    workflows = ROOT / ".github" / "workflows"
    assert not (workflows / "deploy.yml").exists()
    assert not (workflows / "linter.yml").exists()  # redundant Super-Linter retired
    for path in workflows.glob("*.yml"):
        workflow = path.read_text(encoding="utf-8")
        assert "uv run fastapi deploy" not in workflow, path.name
        assert "fastapi cloud env set" not in workflow, path.name
        assert "FASTAPI_CLOUD_TOKEN" not in workflow, path.name
        assert "FASTAPI_CLOUD_APP_ID" not in workflow, path.name


def test_production_smoke_is_independent_of_deployment() -> None:
    smoke = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in smoke
    assert "workflow_call:" in smoke
    assert "workflow_run:" not in smoke


def test_release_dispatch_is_only_for_package_publication() -> None:
    """Keep the package release event; never wire it to a Cloud deployment."""
    semantic = (ROOT / ".github/workflows/semantic-release.yml").read_text(
        encoding="utf-8",
    )
    publishing = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "semantic-release-published" in semantic
    assert "semantic-release-published" in publishing
    assert "Trigger package publishing" in semantic
    assert "production deployment" not in semantic
    assert not (ROOT / ".github/workflows/deploy.yml").exists()
    assert "repository_dispatch:" in publishing


def test_production_smoke_bounds_browser_cost_without_losing_post_deploy_ui_check() -> None:
    smoke = (ROOT / ".github/workflows/master-smoke.yml").read_text(encoding="utf-8")

    assert "pull_request:" in smoke
    assert "workflow_dispatch:" in smoke
    assert "workflow_call:" in smoke
    assert smoke.count("if: github.event_name != 'pull_request'") == 4
    assert "Verify deployed FastAPI Cloud identity and Redis usage" in smoke
    assert "npx --no-install playwright install --with-deps --only-shell chromium" in smoke
    assert "npx playwright install --with-deps chromium" not in smoke
    assert "--omit=dev" in smoke
    assert "timeout-minutes: 6" in smoke
    assert "--retry-all-errors" in smoke
    assert "--connect-timeout 10" in smoke
    assert "--max-time 30" in smoke
    assert "fetch-depth: 0" not in smoke
    assert 'EXPECTED_VERSION="${expected}" node scripts/check-production-api-ui.mjs' in smoke
    assert 'if [[ "${GITHUB_EVENT_NAME}" == "pull_request" ]]' in smoke
    assert ".pfsense.dns.ingress_block.refresh_error" in smoke
    assert '"snort2c refresh is in progress"' in smoke
    assert '.pfsense.dns.ingress_block.cache_layer == "redis"' in smoke


def test_semantic_release_has_bounded_1_5_8_recovery_then_normal_flow() -> None:
    workflow = (ROOT / ".github/workflows/semantic-release.yml").read_text(encoding="utf-8")

    assert "python scripts/check_release_baseline.py" in workflow
    assert "npx semantic-release" in workflow
    assert "semantic-release-published" in workflow
    assert 'SOURCE_VERSION_BEFORE}" == "1.7.0"' in workflow
    assert 'LATEST_RELEASE_TAG}" == "1.5.7"' in workflow
    assert 'RECOVERY_VERSION="1.5.8"' in workflow
    assert "for obsolete_tag in 1.6.0 1.7.0" in workflow
    assert "assert_remote_tag_absent() {" in workflow
    assert 'if git ls-remote --exit-code --tags origin "refs/tags/${tag}"' in workflow
    assert 'if [[ "${status}" -eq 2 ]]' in workflow
    assert "assert_obsolete_recovery_tags_absent() {" in workflow
    assert workflow.count("assert_obsolete_recovery_tags_absent") == 3
    assert 'npm version "${RECOVERY_VERSION}" --no-git-tag-version --ignore-scripts' in workflow
    assert 'python scripts/set_release_version.py "${RECOVERY_VERSION}"' in workflow
    assert 'git tag "${RECOVERY_VERSION}"' in workflow
    assert "git tag --force" not in workflow
    assert "npm pkg delete" not in workflow
    assert "@semantic-release/gitlab" not in workflow


def test_1_5_8_recovery_manifest_documents_consolidation_contract() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    manifest = (ROOT / "docs/release-1.5.8.md").read_text(encoding="utf-8")
    synchronizer = (ROOT / "scripts/set_release_version.py").read_text(encoding="utf-8")

    assert "## [1.5.8]" in changelog
    # The obsolete pre-recovery 1.6.0 was deleted, then 1.6.0 was legitimately
    # published again after the repaired 1.5.8 -> 1.5.10 release sequence.
    assert "compare/1.5.10...1.6.0" in changelog
    # The obsolete pre-recovery 1.7.0 was deleted, but 1.7.0 was later
    # legitimately published again from the repaired release sequence.
    assert "compare/1.6.5...1.7.0" in changelog
    assert "temporarily published as `1.6.0` and `1.7.0`" in manifest
    assert "obsolete tags must still be absent" in manifest
    assert "never force-moves an existing tag" in manifest
    assert "expected exactly one version match" in synchronizer


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
    assert (
        workflow.count(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        )
        == 3
    )
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
    assert ('CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8080/health"]') in dockerfile
    assert "CMD curl --fail" not in dockerfile


def test_ci_uses_current_uv_tooling() -> None:
    python_ci = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    assert 'version: "0.12.22"' in python_ci
    assert 'version: "0.12.1"' not in python_ci


def test_fastapi_cloud_cli_lock_is_current() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert '"fastapi-cloud-cli>=0.26.0"' in project
    assert 'name = "fastapi-cloud-cli"\nversion = "0.26.0"' in lock
    assert 'name = "rich-toolkit"\nversion = "0.20.5"' in lock
    assert 'name = "fastapi-cloud-cli"\nversion = "0.24.0"' not in lock


def test_cloud_debug_is_guarded_by_application_not_deploy_workflow() -> None:
    app_factory = (ROOT / "nabla/app_factory.py").read_text(encoding="utf-8")
    assert 'application_debug_enabled(env_bool("DEBUG"))' in app_factory
    assert not (ROOT / ".github/workflows/deploy.yml").exists()


def test_app_factory_applies_cloud_debug_guard() -> None:
    app_factory = (ROOT / "nabla/app_factory.py").read_text(encoding="utf-8")

    assert 'application_debug_enabled(env_bool("DEBUG"))' in app_factory


def test_deploy_token_not_required_for_github_release_or_smoke() -> None:
    for path in ("semantic-release.yml", "release.yml", "master-smoke.yml"):
        workflow = (ROOT / ".github/workflows" / path).read_text(encoding="utf-8")
        assert "FASTAPI_CLOUD_TOKEN" not in workflow
        assert "fastapi deploy" not in workflow


def test_deployment_revision_artifact_is_included_in_source_bundle() -> None:
    ignored = (ROOT / ".fastapicloudignore").read_text(encoding="utf-8")
    assert "_deployment_revision.py" not in ignored
    assert (ROOT / "nabla/_deployment_revision.py").is_file()
    assert (ROOT / "scripts/stamp_fastapi_deploy_revision.py").is_file()
