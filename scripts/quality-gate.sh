#!/usr/bin/env bash
set -euo pipefail

# Canonical agent/human quality gate. Keep behavior aligned across Nabla
# repositories so local publication policy cannot drift by project.

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "❌ quality-gate.sh must run inside a Git working tree."
    exit 2
}
cd "${ROOT}"

PRE_COMMIT_CMD=()
if [[ -x "${ROOT}/.venv/bin/pre-commit" ]]; then
    PRE_COMMIT_CMD=("${ROOT}/.venv/bin/pre-commit")
elif command -v pre-commit >/dev/null 2>&1; then
    PRE_COMMIT_CMD=(pre-commit)
elif command -v uv >/dev/null 2>&1 && uv run --no-sync pre-commit --version >/dev/null 2>&1; then
    PRE_COMMIT_CMD=(uv run --no-sync pre-commit)
else
    echo "❌ pre-commit is required in the project environment or PATH."
    echo "   Run 'mise run hooks' after syncing the development environment."
    exit 2
fi

EDITORCONFIG_CMD=()
if [[ -f "${ROOT}/.editorconfig" ]]; then
    if command -v ec >/dev/null 2>&1; then
        EDITORCONFIG_CMD=(ec)
    elif command -v editorconfig-checker >/dev/null 2>&1; then
        EDITORCONFIG_CMD=(editorconfig-checker)
    elif command -v uvx >/dev/null 2>&1; then
        # Pin the same checker family used by MegaLinter so the local gate catches
        # EditorConfig violations before push. editorconfig-checker validates; it
        # does not rewrite arbitrary indentation errors automatically.
        EDITORCONFIG_CMD=(uvx --from editorconfig-checker==3.11.1 ec)
    else
        echo "❌ editorconfig-checker is required when .editorconfig is present."
        echo "   Install editorconfig-checker or uv, then rerun scripts/quality-gate.sh."
        exit 2
    fi
fi

verified_commit_ref() {
    git rev-parse --verify --quiet "${1}^{commit}" >/dev/null 2>&1
}

closest_remote_default_ref() {
    local candidate distance best_ref="" best_distance=""
    for candidate in origin/master origin/main; do
        if ! verified_commit_ref "${candidate}"; then
            continue
        fi
        distance="$(git rev-list --count "${candidate}...HEAD")"
        if [[ -z "${best_distance}" || "${distance}" -lt "${best_distance}" ]]; then
            best_ref="${candidate}"
            best_distance="${distance}"
        fi
    done
    if [[ -n "${best_ref}" ]]; then
        printf '%s\n' "${best_ref}"
    fi
    return 0
}

resolve_base_ref() {
    local configured origin_head candidate
    configured="${QUALITY_BASE_REF:-}"
    if [[ -n "${configured}" ]]; then
        if ! verified_commit_ref "${configured}"; then
            echo "❌ QUALITY_BASE_REF does not resolve to a commit: ${configured}" >&2
            return 2
        fi
        printf '%s\n' "${configured}"
        return
    fi

    if origin_head="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)" \
        && verified_commit_ref "${origin_head}"; then
        printf '%s\n' "${origin_head}"
        return
    fi

    candidate="$(closest_remote_default_ref)"
    if [[ -n "${candidate}" ]]; then
        printf '%s\n' "${candidate}"
    elif verified_commit_ref HEAD~1; then
        printf '%s\n' "HEAD~1"
    else
        printf '%s\n' "HEAD"
    fi
}

BASE_REF="$(resolve_base_ref)"
echo "📐 Comparing changed files against ${BASE_REF}."

mapfile -t CHANGED_FILES < <(
    {
        if [[ "${BASE_REF}" != "HEAD" ]]; then
            git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
        fi
        git diff --name-only --diff-filter=ACMR
        git diff --cached --name-only --diff-filter=ACMR
        git ls-files --others --exclude-standard
    } | awk 'NF' | sort -u | while IFS= read -r file; do
        [[ -f "${file}" ]] && printf '%s\n' "${file}"
    done
)

if ((${#CHANGED_FILES[@]} > 0)); then
    echo "🔧 Running repository formatters and linters on changed files..."
    if ! "${PRE_COMMIT_CMD[@]}" run \
        --hook-stage pre-commit \
        --files "${CHANGED_FILES[@]}" \
        --show-diff-on-failure; then
        echo "❌ Pre-commit changed files or found validation errors."
        echo "   Review/fix the output, then run scripts/quality-gate.sh again."
        git status --short
        exit 1
    fi

    if ((${#EDITORCONFIG_CMD[@]} > 0)); then
        echo "📏 Checking EditorConfig rules on changed files..."
        if ! "${EDITORCONFIG_CMD[@]}" -config "${ROOT}/.editorconfig-checker.json" "${CHANGED_FILES[@]}"; then
            echo "❌ EditorConfig validation failed."
            echo "   Fix the reported formatting manually, then rerun scripts/quality-gate.sh."
            exit 1
        fi
    fi
else
    echo "✅ No changed files require formatter/linter validation."
fi

echo "🔍 Checking whitespace errors..."
git diff --check
git diff --cached --check

STATUS="$(git status --short)"
if [[ -n "${STATUS}" ]]; then
    echo "❌ Working tree is not clean after quality validation."
    echo "   Review and commit generated/fixed files, then run scripts/quality-gate.sh again."
    printf '%s\n' "${STATUS}"
    exit 1
fi

echo "✅ Quality gate passed; repository is clean and ready to publish."
