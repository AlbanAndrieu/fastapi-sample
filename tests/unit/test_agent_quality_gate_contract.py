"""Contract tests for the agent-first pre-build quality gate."""

from __future__ import annotations

import stat
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_dependency_updates_are_explicit_maintenance_not_validation() -> None:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    updater = next(hook for hook in hooks if hook["id"] == "pre-commit-update")
    assert updater["stages"] == ["manual"]
    for hook_id in ("prettier", "yamllint", "ruff-check", "bandit"):
        hook = next(hook for hook in hooks if hook["id"] == hook_id)
        assert "stages" not in hook or "pre-commit" in hook["stages"]


def test_agent_quality_gate_wraps_tests_and_canonical_gate() -> None:
    gate = ROOT / "scripts" / "agent-quality-gate.sh"
    mode = stat.S_IMODE(gate.stat().st_mode)
    text = gate.read_text(encoding="utf-8")

    assert mode & stat.S_IXUSR
    assert "QG_BASE_STALE" in text
    assert "QG_LARGE_DELETION" in text
    assert "diff-filter=D" in text
    assert "QG_EXEC_BIT" in text
    assert "QG_FIX_NO_PROGRESS" in text
    assert "QG_FIX_NOT_CONVERGED" in text
    assert "QUALITY_FIX_PASSES" in text
    assert "worktree_fingerprint" in text
    assert "git hash-object --stdin" in text
    assert "--dependency-mode" in text
    assert "--ci-preflight" in text
    assert 'echo "full"' in text
    assert 'echo "quality"' in text
    assert 'echo "none"' in text
    assert "uv run pre-commit run shfmt" in text
    assert "uv run pre-commit run shell-lint" in text
    assert "uv run pre-commit run bashate" in text
    assert "uv run pytest -q --disable-warnings --maxfail=1 --junit-xml=junit.xml" in text
    assert "quality-gate contract pytest (isolated fail-fast)" in text
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in text
    assert "uv run pytest -q --noconftest" in text
    assert "tests/unit/test_agent_quality_gate_contract.py --junit-xml=junit.xml" in text
    assert "dependency-backed tests are still required" in text
    assert "full_pytest_impact" in text
    assert "quality_contract_impact" in text
    assert "uv run python scripts/check_versions.py" in text
    assert "bash scripts/quality-gate.sh --publish" in text
    assert "modified Python code-size gate" in text
    assert "uv run python scripts/check_code_size.py" in text
    assert text.index("canonical formatter/linter/security") < text.index(
        "modified Python code-size gate",
    )
    assert text.index("modified Python code-size gate") < text.index(
        "quality-gate contract pytest (isolated fail-fast)",
    )
    assert "Working tree changed after tests" in text
    assert 'tail -n "${LOG_TAIL}"' in text
    assert "LOG_TAIL=80" in text


def test_pre_push_uses_agent_publication_gate() -> None:
    config = (ROOT / ".pre-commit-pre-push.yaml").read_text(encoding="utf-8")

    assert "entry: bash scripts/agent-quality-gate.sh --publish" in config


def test_python_ci_runs_fast_gate_before_heavy_dependency_sync() -> None:
    workflow = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")

    assert "\n  preflight:\n" in workflow
    assert "Fast deterministic quality gate" in workflow
    assert "Create minimal quality environment" in workflow
    assert "uv venv --python" in workflow
    assert "pre-commit==4.6.2" in workflow
    assert "enable-cache: false" in workflow
    assert 'UV_NO_SYNC: "1"' in workflow
    assert 'SKIP: "uv-sync,uv-lock,uv-export,pytest-collect"' in workflow
    assert "run: bash scripts/agent-quality-gate.sh --ci-preflight" in workflow
    assert "Resolve and install locked project dependencies" in workflow
    assert "run: uv sync --frozen" in workflow
    assert "Run repository pytest suite after dependency sync" in workflow
    assert "uv run --no-sync pytest -q --disable-warnings --maxfail=1" in workflow
    assert workflow.index("Run agent CI preflight before project dependency sync") < workflow.index(
        "Resolve and install locked project dependencies",
    )
    assert workflow.index("Resolve and install locked project dependencies") < workflow.index(
        "Run repository pytest suite after dependency sync",
    )
    assert "workflow_dispatch:" in workflow
    assert "format('origin/{0}', github.base_ref)" in workflow
    assert "'origin/master'" in workflow
    assert "\n    needs: preflight\n" in workflow
    assert "\n    needs: build\n" in workflow
    reusable_condition = "github.event_name != 'pull_request' || github.event.pull_request.draft == false"
    assert workflow.count(reusable_condition) == 2
    assert workflow.count("Upload test results to Trunk.io") == 1
    assert "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9" in workflow
    assert "actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9" in workflow
    assert "steps.precommit-cache.outputs.cache-hit != 'true'" in workflow
    assert "path: ~/.cache/pre-commit" in workflow
    assert "Ruff critical checks" not in workflow
    assert "Bandit security report" not in workflow


def test_production_smoke_does_not_run_on_every_pr_synchronize() -> None:
    workflow = (ROOT / ".github/workflows/production-smoke.yml").read_text(
        encoding="utf-8",
    )

    assert "types: [opened, ready_for_review]" in workflow
    assert "synchronize" not in workflow.split("jobs:", maxsplit=1)[0]
    assert "github.event.pull_request.draft == false" in workflow


def test_codeql_waits_until_draft_is_ready() -> None:
    workflow = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")

    assert "types: [opened, synchronize, reopened, ready_for_review]" in workflow
    assert "github.event.pull_request.draft == false" in workflow


def test_canonical_quality_gate_has_explicit_publication_mode() -> None:
    gate = (ROOT / "scripts" / "quality-gate.sh").read_text(encoding="utf-8")

    assert 'if [[ "${1:-}" == "--publish" ]]' in gate
    assert "Working tree is not clean enough to publish" in gate
    assert "Quality gate passed. Review and commit validated changes before publishing." in gate


def test_mise_exposes_agent_fix_check_and_publish_tasks() -> None:
    config = (ROOT / "mise.toml").read_text(encoding="utf-8")

    assert "[tasks.agent-fix]" in config
    assert "[tasks.agent-quality]" in config
    assert "[tasks.agent-publish]" in config
    assert 'run = "bash scripts/agent-quality-gate.sh --publish"' in config


def test_megalinter_caller_keeps_least_privilege_permissions() -> None:
    workflow = (ROOT / ".github/workflows/python.yml").read_text(encoding="utf-8")
    caller = workflow.split("\n  mega-linter:\n", maxsplit=1)[1]

    assert "contents: read" in caller
    assert "security-events: write" in caller
    assert "pull-requests: write" not in caller
    assert "issues: write" not in caller
    assert "statuses: write" not in caller


def test_release_publishes_immutable_ghcr_image() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "\n  publish_container:\n" in workflow
    assert "Publish immutable GHCR image" in workflow
    assert "packages: write" in workflow
    assert "ghcr.io/${owner_lc}/fastapi-sample" in workflow
    assert "version_tag=${repository}:${RELEASE_TAG}" in workflow
    assert "latest_tag=${repository}:latest" in workflow
    assert "push: true" in workflow
    assert "cache-from: type=gha,scope=production" in workflow
    assert "cache-to: type=gha,mode=max,scope=production" in workflow


def test_agent_completion_policy_requires_roadmap_accounting() -> None:
    guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "engineering-roadmap.md").read_text(encoding="utf-8")
    fastapi_cloud_skill = (ROOT / ".agents" / "skills" / "fastapi-cloud" / "SKILL.md").read_text(encoding="utf-8")
    homelab_skill = next((ROOT / ".agents" / "skills" / "homelab-runtime-status").glob("SKILL.md*")).read_text(encoding="utf-8")

    assert "must not declare work complete" in guide.lower()
    assert "docs/engineering-roadmap.md" in guide
    assert "known residual" in guide.lower()
    assert "next acceptance proof" in guide.lower()

    assert "completion gate" in fastapi_cloud_skill.lower()
    assert "docs/engineering-roadmap.md" in fastapi_cloud_skill
    assert "completion gate" in homelab_skill.lower()
    assert "docs/engineering-roadmap.md" in homelab_skill

    assert "P0 — TrueNAS-local dependency convergence" in roadmap
    assert "pfSense posture API" in roadmap
    assert "Prometheus runtime configuration" in roadmap
    assert "Cloudflare control-plane evidence" in roadmap
    assert "Sentry application acceptance" in roadmap
    assert "Pyroscope application acceptance" in roadmap


def test_zap_runs_only_post_merge_or_manually_against_production_surfaces() -> None:
    workflow_text = (ROOT / ".github/workflows/security-zap.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow_text.split("jobs:", maxsplit=1)[0]
    dast_env = workflow["jobs"]["dast"]["env"]

    assert "pull_request:" not in triggers
    assert "workflow_call:" in triggers
    assert "workflow_dispatch:" in triggers
    assert "127.0.0.1" not in workflow_text
    assert "uvicorn" not in workflow_text
    assert dast_env["TRUENAS_ROOT_URL"] == "https://sample.albandrieu.com/"
    assert dast_env["TRUENAS_API_URL"] == "https://sample.albandrieu.com/api"
    assert dast_env["TRUENAS_OPENAPI_URL"] == "https://sample.albandrieu.com/openapi.json"
    assert dast_env["CLOUD_API_URL"] == "https://fastapi-sample.fastapicloud.dev/api"
    assert dast_env["CLOUD_OPENAPI_URL"] == "https://fastapi-sample.fastapicloud.dev/openapi.json"
    assert "CF-Access-Client-Id" in workflow_text
    assert "CF-Access-Client-Secret" in workflow_text
    assert "Management APIs for pfSense and TrueNAS are intentionally excluded" in workflow_text
    assert workflow_text.count("fail_action: true") == 5
    assert "zap-web-truenas-root" in workflow_text
    assert "zap-web-truenas-api" in workflow_text
    assert "zap-web-fastapi-cloud-api" in workflow_text
    assert "zap-api-truenas" in workflow_text
    assert "zap-api-fastapi-cloud" in workflow_text


def test_master_red_remediation_is_post_merge_and_deduplicated() -> None:
    workflow = (ROOT / ".github" / "workflows" / "master-red-remediation.yml").read_text(
        encoding="utf-8",
    )

    assert "name: Master red remediation" in workflow
    assert "branches: [master]" in workflow
    assert "workflow_dispatch:" in workflow
    assert "uses: ./.github/workflows/python.yml" in workflow
    assert "uses: ./.github/workflows/production-smoke.yml" in workflow
    assert "uses: ./.github/workflows/codeql.yml" in workflow
    assert "uses: ./.github/workflows/security-zap.yml" in workflow
    assert "needs: [classify, production-smoke]" in workflow
    assert "needs.production-smoke.result == 'success'" in workflow
    assert "secrets: inherit" not in workflow
    assert "needs: [classify, python, production-smoke, codeql, zap]" in workflow
    assert "needs.python.result != 'success'" in workflow
    assert "needs.production-smoke.result != 'success'" in workflow
    assert "MASTER_REMEDIATION_TOKEN" in workflow
    assert "issues: write" in workflow
    assert "pull-requests: write" in workflow
    assert "contents: write" in workflow
    assert "[master-red:${short_sha}]" in workflow
    assert "remediation/master-red-${short_sha}" in workflow
    assert "docs/remediation/master-red-${short_sha}.md" in workflow
    assert "Do not merge this PR while it only contains this evidence file" in workflow
    assert "docs/engineering-roadmap.md" in workflow
    assert "Keep red master visible until remediation" in workflow
