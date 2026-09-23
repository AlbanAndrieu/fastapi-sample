#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "\${ROOT}"

MODE_ONLY=false
if [[ "\${1:-}" == "--mode-only" ]]; then
    MODE_ONLY=true
    shift
fi
if (($# > 2)); then
    echo "usage: $0 [--mode-only] [BASE_REF] [HEAD_REF]" >&2
    exit 2
fi

resolve_base_ref() {
    if [[ -n "\${QUALITY_BASE_REF:-}" ]]; then
        printf '%s\n' "\${QUALITY_BASE_REF}"
    elif git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
        git symbolic-ref --quiet --short refs/remotes/origin/HEAD
    elif git rev-parse --verify origin/master >/dev/null 2>&1; then
        printf '%s\n' "origin/master"
    elif git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
        printf '%s\n' "HEAD~1"
    else
        printf '%s\n' "HEAD"
    fi
}

BASE_REF="\${1:-$(resolve_base_ref)}"
HEAD_REF="\${2:-HEAD}"

for ref in "\${BASE_REF}" "\${HEAD_REF}"; do
    if ! git rev-parse --verify "\${ref}^{commit}" >/dev/null 2>&1; then
        printf '❌ CI_SCOPE_REF_MISSING: %s\n' "\${ref}" >&2
        exit 1
    fi
done

collect_changed_files() {
    {
        if [[ "\${BASE_REF}" != "\${HEAD_REF}" ]]; then
            git diff --name-only --diff-filter=ACMRD "\${BASE_REF}...\${HEAD_REF}"
        fi
        if [[ "\${HEAD_REF}" == "HEAD" ]]; then
            git diff --name-only --diff-filter=ACMRD
            git diff --cached --name-only --diff-filter=ACMRD
            git ls-files --others --exclude-standard
        fi
    } | awk 'NF' | sort -u
}

is_docs_only_path() {
    case "$1" in
        docs/* | *.md)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

is_quality_only_path() {
    case "$1" in
        tests/unit/test_agent_quality_gate_contract.py | \
            tests/unit/test_agent_dependency_mode.py | \
            tests/unit/test_agent_publication_proof.py | \
            tests/unit/test_ci_scope.py | \
            tests/unit/test_ci_performance_budget.py | \
            scripts/agent-quality-gate.sh | \
            scripts/agent-publish.sh | \
            scripts/quality-gate.sh | \
            scripts/check_code_size.py | \
            scripts/ci-scope.sh | \
            scripts/ci-performance-budget.sh | \
            .github/workflows/* | \
            .pre-commit-config.yaml | \
            .pre-commit-pre-push.yaml | \
            mise.toml | \
            AGENTS.md)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

mapfile -t CHANGED_FILES < <(collect_changed_files)

dependency_mode="none"
quality_change=false
for file in "\${CHANGED_FILES[@]}"; do
    if is_docs_only_path "\${file}"; then
        continue
    fi
    if is_quality_only_path "\${file}"; then
        quality_change=true
        continue
    fi
    dependency_mode="full"
    break
done

if [[ "\${dependency_mode}" != "full" && "\${quality_change}" == true ]]; then
    dependency_mode="quality"
fi

if [[ "\${MODE_ONLY}" == true ]]; then
    printf '%s\n' "\${dependency_mode}"
    exit 0
fi

printf 'dependency_mode=%s\n' "\${dependency_mode}"
printf 'changed_count=%d\n' "\${#CHANGED_FILES[@]}"

if [[ -n "\${GITHUB_OUTPUT:-}" ]]; then
    {
        printf 'dependency_mode=%s\n' "\${dependency_mode}"
        printf 'changed_count=%d\n' "\${#CHANGED_FILES[@]}"
    } >>"\${GITHUB_OUTPUT}"
fi

case "\${dependency_mode}" in
    full)
        echo "ℹ️ CI scope: application/runtime/security-capable change; full dependency path required."
        ;;
    quality)
        echo "ℹ️ CI scope: quality infrastructure only; isolated quality contracts are sufficient."
        ;;
    none)
        echo "ℹ️ CI scope: documentation-only or empty diff; project dependency bootstrap may be skipped."
        ;;
esac
