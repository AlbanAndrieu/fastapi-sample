"""Classify changed files into FastAPI CI/security work scopes."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    maintenance_only: bool
    application: bool
    sast: bool
    build: bool
    dependencies: bool
    dependency_mode: str
    changed_count: int


QUALITY_MAINTENANCE_PATHS = {
    ".pre-commit-config.yaml",
    ".pre-commit-pre-push.yaml",
    "AGENTS.md",
    "mise.toml",
    "scripts/agent-publish.sh",
    "scripts/agent-quality-gate.sh",
    "scripts/check_code_size.py",
    "scripts/quality-gate.sh",
    "tests/unit/test_agent_dependency_mode.py",
    "tests/unit/test_agent_publication_proof.py",
    "tests/unit/test_agent_quality_gate_contract.py",
    "tests/unit/test_ci_scope.py",
}

SECURITY_NON_DEPLOYABLE_PATHS = {
    "scripts/ci_scope.py",
}


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _has_commit(ref: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return completed.returncode == 0


def resolve_base_ref() -> str:
    if override := os.environ.get("QUALITY_BASE_REF"):
        return override
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if symbolic.returncode == 0 and symbolic.stdout.strip():
        return symbolic.stdout.strip()
    if _has_commit("origin/master"):
        return "origin/master"
    if _has_commit("HEAD~1"):
        return "HEAD~1"
    return "HEAD"


def changed_files(base_ref: str, head_ref: str) -> tuple[str, ...]:
    if not _has_commit(base_ref):
        raise SystemExit(f"CI_SCOPE_BASE_MISSING: {base_ref}")
    if not _has_commit(head_ref):
        raise SystemExit(f"CI_SCOPE_HEAD_MISSING: {head_ref}")

    paths = set(
        line
        for line in _git(
            "diff",
            "--name-only",
            "--diff-filter=ACMRD",
            base_ref,
            head_ref,
        ).splitlines()
        if line
    )
    if head_ref == "HEAD":
        for args in (
            ("diff", "--name-only", "--diff-filter=ACMRD"),
            ("diff", "--cached", "--name-only", "--diff-filter=ACMRD"),
            ("ls-files", "--others", "--exclude-standard"),
        ):
            paths.update(line for line in _git(*args).splitlines() if line)
    return tuple(sorted(paths))


def _is_docs_path(path: str) -> bool:
    return path.startswith("docs/") or path.endswith(".md")


def _is_quality_maintenance_path(path: str) -> bool:
    return path in QUALITY_MAINTENANCE_PATHS


def _is_security_non_deployable_path(path: str) -> bool:
    return (
        path in SECURITY_NON_DEPLOYABLE_PATHS
        or path.startswith(".github/")
        or path.startswith(".zap/")
    )


def _is_test_path(path: str) -> bool:
    return path.startswith("tests/")


def classify(paths: tuple[str, ...]) -> Scope:
    if not paths:
        return Scope(
            maintenance_only=False,
            application=True,
            sast=True,
            build=True,
            dependencies=True,
            dependency_mode="full",
            changed_count=0,
        )

    maintenance_only = True
    application = False
    sast = False
    build = False
    dependencies = False
    quality_contract = False

    for path in paths:
        if _is_quality_maintenance_path(path):
            quality_contract = True
            continue
        if _is_docs_path(path):
            continue

        maintenance_only = False
        if _is_security_non_deployable_path(path):
            quality_contract = True
            sast = True
            continue
        if _is_test_path(path):
            sast = True
            dependencies = True
            continue

        application = True
        sast = True
        build = True
        dependencies = True

    if application or dependencies:
        dependency_mode = "full"
    elif quality_contract:
        dependency_mode = "quality"
    else:
        dependency_mode = "none"

    return Scope(
        maintenance_only=maintenance_only,
        application=application,
        sast=sast,
        build=build,
        dependencies=dependencies,
        dependency_mode=dependency_mode,
        changed_count=len(paths),
    )


def _as_bool(value: bool) -> str:
    return "true" if value else "false"


def render(scope: Scope) -> str:
    return "\n".join(
        (
            f"maintenance_only={_as_bool(scope.maintenance_only)}",
            f"application={_as_bool(scope.application)}",
            f"sast={_as_bool(scope.sast)}",
            f"build={_as_bool(scope.build)}",
            f"dependencies={_as_bool(scope.dependencies)}",
            f"dependency_mode={scope.dependency_mode}",
            f"changed_count={scope.changed_count}",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-mode", action="store_true")
    parser.add_argument("base_ref", nargs="?")
    parser.add_argument("head_ref", nargs="?", default="HEAD")
    args = parser.parse_args()

    base_ref = args.base_ref or resolve_base_ref()
    scope = classify(changed_files(base_ref, args.head_ref))
    if args.dependency_mode:
        print(scope.dependency_mode)
        return 0

    output = render(scope)
    print(output)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"{output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
