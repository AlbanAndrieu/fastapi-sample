#!/usr/bin/env bash
set -euo pipefail

# Agent/human quality gate to run before every push.
# This phase may apply safe formatting/fixes; if it changes files, commit them and
# run the gate again before pushing.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BASE_REF="${QUALITY_BASE_REF:-origin/main}"
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    BASE_REF="HEAD~1"
fi

mapfile -t PYTHON_FILES < <(
    git diff --name-only --diff-filter=ACMR "$BASE_REF...HEAD" -- '*.py' |
        while IFS= read -r file; do
            [[ -f "$file" ]] && printf '%s\n' "$file"
        done
)

echo "🔧 Running safe local auto-fixes before push..."
if (( ${#PYTHON_FILES[@]} )); then
    uv run ruff check --fix -- "${PYTHON_FILES[@]}"
    uv run ruff format -- "${PYTHON_FILES[@]}"
fi

# Run the repository's existing pre-commit policy only for the branch diff.
# Explicit pre-commit stage avoids recursion with the pre-push hook.
echo "🔍 Running pre-commit policy on branch changes..."
uv run pre-commit run --hook-stage pre-commit --from-ref "$BASE_REF" --to-ref HEAD

echo "🔍 Verifying Ruff after auto-fixes..."
if (( ${#PYTHON_FILES[@]} )); then
    uv run ruff format --check -- "${PYTHON_FILES[@]}"
    uv run ruff check -- "${PYTHON_FILES[@]}"
fi

echo "🔒 Checking dependency lock consistency..."
uv lock --check

echo "🧪 Running fast test gate..."
uv run pytest -q --disable-warnings --maxfail=1

echo "🔍 Checking whitespace and generated modifications..."
git diff --check

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "❌ Quality tools changed tracked files or staged changes remain."
    echo "   Review the changes, commit them, then run scripts/quality-gate.sh again."
    git status --short
    exit 1
fi

echo "✅ Quality gate passed; repository is clean and ready to push."
