#!/usr/bin/env bash
set -euo pipefail

# Strict, check-only gate invoked by .githooks/pre-push.
# It intentionally performs no explicit Ruff fixes. Existing pre-commit hooks may
# still propose edits; any resulting dirty tree blocks the push.

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

echo "🚦 Pre-push quality gate"

if (( ${#PYTHON_FILES[@]} )); then
    echo "🔍 Ruff format check..."
    uv run ruff format --check -- "${PYTHON_FILES[@]}"
    echo "🔍 Ruff lint check..."
    uv run ruff check -- "${PYTHON_FILES[@]}"
fi

echo "🔍 Repository pre-commit policy..."
uv run pre-commit run --hook-stage pre-commit --from-ref "$BASE_REF" --to-ref HEAD

echo "🔒 uv.lock consistency..."
uv lock --check

echo "🧪 Fast test gate..."
uv run pytest -q --disable-warnings --maxfail=1

git diff --check
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "❌ Pre-push checks modified files or found uncommitted changes."
    echo "   Run scripts/quality-gate.sh, review/commit its fixes, then push again."
    git status --short
    exit 1
fi

echo "✅ Pre-push quality gate passed."
