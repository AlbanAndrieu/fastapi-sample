#!/usr/bin/env bash
set -euo pipefail

# Bababou-style dependency-free L1 fallback; never a substitute for quality gate.
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
MAX_PATHS="${AGENT_OFFLINE_MAX_PATHS:-0}"
if [[ ! "$MAX_PATHS" =~ ^(0|[1-9][0-9]*)$ ]]; then
    echo "❌ OFFLINE_LIMIT_INVALID: expected zero or positive integer" >&2
    exit 2
fi
BASE="${QUALITY_BASE_REF:-}"
if [[ -z "$BASE" ]]; then
    for candidate in origin/master master; do
        if git rev-parse --verify "$candidate^{commit}" >/dev/null 2>&1; then
            BASE="$candidate"
            break
        fi
    done
fi

scope_file="$(mktemp)"
trap 'rm -f "$scope_file"' EXIT
base_available=false
if [[ -n "$BASE" ]] && git rev-parse --verify "$BASE^{commit}" >/dev/null 2>&1 \
    && git merge-base "$BASE" HEAD >/dev/null 2>&1; then
    base_available=true
fi
if [[ "$base_available" == true ]]; then
    {
        git diff --name-only --diff-filter=ACMR "$BASE...HEAD"
        git diff --name-only --diff-filter=ACMR
        git diff --cached --name-only --diff-filter=ACMR
        git ls-files --others --exclude-standard
    } | LC_ALL=C sort -u > "$scope_file"
    printf 'ℹ️ OFFLINE_SCOPE_DIFF: %s...HEAD + worktree\n' "$BASE"
else
    {
        git ls-files
        git ls-files --others --exclude-standard
    } | LC_ALL=C sort -u > "$scope_file"
    echo "⚠️ OFFLINE_BASE_UNAVAILABLE: full local files only; PR comparison not verified" >&2
fi

mapfile -t files < "$scope_file"
if ((MAX_PATHS > 0 && ${#files[@]} > MAX_PATHS)); then
    printf '❌ OFFLINE_LIMIT_EXCEEDED: %d > %d\n' "${#files[@]}" "$MAX_PATHS" >&2
    exit 2
fi
checked=0
for file in "${files[@]}"; do
    [[ -f "$file" && ! -L "$file" ]] || continue
    case "$file" in
        *.sh)
            bash -n "$file"
            checked=$((checked + 1))
            ;;
        *.py)
            python3 -c 'import ast,sys; from pathlib import Path; ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"),filename=sys.argv[1])' "$file"
            checked=$((checked + 1))
            ;;
        *.json)
            python3 -c 'import json,sys; from pathlib import Path; json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))' "$file"
            checked=$((checked + 1))
            ;;
        *.mjs|*.cjs)
            if ! command -v node >/dev/null 2>&1; then
                echo "❌ OFFLINE_NODE_MISSING" >&2
                exit 2
            fi
            node --check "$file"
            checked=$((checked + 1))
            ;;
    esac
done
if [[ "$base_available" == true ]]; then
    git diff --check "$BASE...HEAD"
fi
git diff --check
git diff --cached --check
python3 scripts/ci/check_draft_workflows.py
printf '✅ OFFLINE_L1_PASS: paths=%d syntax_checked=%d\n' "${#files[@]}" "$checked"
echo "⚠️ NOT_RUN: pre-commit, Ruff, Betterleaks, dependencies, full tests and CI"
