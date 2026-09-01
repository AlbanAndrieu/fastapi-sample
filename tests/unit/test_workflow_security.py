"""Security regression tests for GitHub Actions workflow references."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CODEQL_ACTION_SHA = "cdf488f595d80d6e07e03d4674febd5ab45fa938"
IMMUTABLE_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _workflow_texts() -> list[tuple[Path, str]]:
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.yml"))
    ]


def test_codeql_python_uses_consistent_v4_no_build_mode() -> None:
    workflow = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")

    assert f"github/codeql-action/init@{CODEQL_ACTION_SHA} # v4.37.9" in workflow
    assert f"github/codeql-action/analyze@{CODEQL_ACTION_SHA} # v4.37.9" in workflow
    assert "build-mode: none" in workflow
    assert "github/codeql-action/autobuild@" not in workflow
    assert "# v3." not in workflow


def test_all_codeql_actions_use_the_same_v4_release() -> None:
    codeql_lines = [
        line.strip()
        for _, text in _workflow_texts()
        for line in text.splitlines()
        if "uses: github/codeql-action/" in line
    ]

    assert codeql_lines
    for line in codeql_lines:
        assert f"@{CODEQL_ACTION_SHA}" in line
        assert "# v4.37.9" in line


def test_external_workflow_actions_are_pinned_to_immutable_shas() -> None:
    unpinned: list[str] = []
    for path, text in _workflow_texts():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            target = stripped.removeprefix("uses:").split("#", maxsplit=1)[0].strip()
            target = target.strip("'\"")
            if target.startswith("./"):
                continue
            _, separator, ref = target.rpartition("@")
            if not separator or IMMUTABLE_SHA_RE.fullmatch(ref) is None:
                unpinned.append(f"{path.relative_to(ROOT)}: {target}")

    assert not unpinned, "Unpinned GitHub Actions:\n" + "\n".join(unpinned)


def test_renovate_app_token_is_least_privilege_and_checkout_is_hardened() -> None:
    workflow = (WORKFLOWS / "renovate.yml").read_text(encoding="utf-8")
    token_step = workflow.split("- name: Create GitHub App token", maxsplit=1)[1].split(
        "- name: Checkout", maxsplit=1
    )[0]
    checkout = workflow.split("- name: Checkout", maxsplit=1)[1].split(
        "- name: Self-hosted Renovate", maxsplit=1
    )[0]

    expected_permissions = {
        "permission-checks: write",
        "permission-contents: write",
        "permission-issues: write",
        "permission-pull-requests: write",
        "permission-statuses: write",
        "permission-workflows: write",
    }
    assert all(permission in token_step for permission in expected_permissions)
    assert "persist-credentials: false" in checkout


def test_dependabot_groups_codeql_subactions_atomically() -> None:
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    github_actions = dependabot.split(
        '- package-ecosystem: "github-actions"', maxsplit=1
    )[1].split('# Enable version updates for npm', maxsplit=1)[0]

    assert "groups:" in github_actions
    assert "codeql-action:" in github_actions
    assert '- "github/codeql-action/*"' in github_actions
