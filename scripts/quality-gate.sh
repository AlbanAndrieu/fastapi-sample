#!/usr/bin/env bash
set -euo pipefail

# Canonical agent/human quality gate. Keep behavior aligned across Nabla
# repositories so local publication policy cannot drift by project.

PUBLISH=false
if [[ "${1:-}" == "--publish" ]]; then
    PUBLISH=true
    shift
fi
if (($# > 0)); then
    echo "usage: $0 [--publish]" >&2
    exit 2
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "❌ quality-gate.sh must run inside a Git working tree."
    exit 2
}
cd "${ROOT}"

PRE_COMMIT_CMD=()
if [[ -x "${ROOT}/.venv/bin/prek" ]]; then
    PRE_COMMIT_CMD=("${ROOT}/.venv/bin/prek")
elif command -v prek >/dev/null 2>&1; then
    PRE_COMMIT_CMD=(prek)
elif command -v uv >/dev/null 2>&1 && uv run --no-sync prek --version >/dev/null 2>&1; then
    PRE_COMMIT_CMD=(uv run --no-sync prek)
else
    echo "❌ prek is required in the project environment or PATH."
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
        EDITORCONFIG_CMD=(uvx --from editorconfig-checker==3.11.1 ec)
    elif command -v uv >/dev/null 2>&1; then
        # uvx is an alias for `uv tool run`, but uv-only installs lack uvx.
        EDITORCONFIG_CMD=(uv tool run --from editorconfig-checker==3.11.1 ec)
    else
        echo "❌ editorconfig-checker is required when .editorconfig is present."
        echo "   Install editorconfig-checker or uv, then rerun scripts/quality-gate.sh."
        exit 2
    fi
fi

# Reuse the same base selection as agent checks and publication.
# shellcheck source=scripts/ci/quality-git.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/ci/quality-git.sh"
BASE_REF="$(quality_resolve_base_ref)"
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
    echo "🔧 Running repository formatters and linters on ${#CHANGED_FILES[@]} changed file(s)..."
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

if [[ "${PUBLISH}" == true ]]; then
    STATUS="$(git status --short)"
    if [[ -n "${STATUS}" ]]; then
        echo "❌ Working tree is not clean enough to publish."
        echo "   Review and commit generated/fixed files, then run scripts/quality-gate.sh --publish again."
        printf '%s\n' "${STATUS}"
        exit 1
    fi
    echo "✅ Publication quality gate passed; repository is clean and ready to publish."
else
    echo "✅ Quality gate passed. Review and commit validated changes before publishing."
fi
