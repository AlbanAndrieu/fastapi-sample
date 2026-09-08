#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

MODE="check"
PUBLISH=false
case "${1:-}" in
    --fix)
        MODE="fix"
        shift
        ;;
    --publish)
        PUBLISH=true
        shift
        ;;
    -h | --help)
        cat <<'EOF'
Usage:
  bash scripts/agent-quality-gate.sh [--fix|--publish]

Modes:
  default    strict validation gate
  --fix      apply/check pre-commit hooks on the complete change set first
  --publish  strict gate plus canonical clean-tree publication check

Environment:
  QUALITY_BASE_REF                 override comparison base
  QUALITY_LOG_TAIL                 failure log lines to print (default: 80)
  QUALITY_ALLOW_LARGE_DELETION=1   acknowledge an intentional large truncation/deletion
EOF
        exit 0
        ;;
    "")
        ;;
    *)
        printf '❌ unknown argument: %s\n' "$1" >&2
        exit 2
        ;;
esac

if (($# > 0)); then
    printf '❌ unexpected argument: %s\n' "$1" >&2
    exit 2
fi

LOG_TAIL="${QUALITY_LOG_TAIL:-80}"

resolve_base_ref() {
    if [[ -n "${QUALITY_BASE_REF:-}" ]]; then
        printf '%s\n' "${QUALITY_BASE_REF}"
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

BASE_REF="$(resolve_base_ref)"

run_compact() {
    local label="$1"
    shift
    local log
    local rc
    log="$(mktemp)"
    if "$@" >"${log}" 2>&1; then
        rm -f "${log}"
        printf '✅ %s\n' "${label}"
        return 0
    else
        rc=$?
    fi
    printf '❌ %s\n' "${label}" >&2
    tail -n "${LOG_TAIL}" "${log}" >&2 || true
    rm -f "${log}"
    return "${rc}"
}

collect_changed_files() {
    {
        if [[ "${BASE_REF}" != "HEAD" ]] && git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
            git diff --name-only --diff-filter=ACMR "${BASE_REF}...HEAD"
        fi
        git diff --name-only --diff-filter=ACMR
        git diff --cached --name-only --diff-filter=ACMR
        git ls-files --others --exclude-standard
    } |
        awk 'NF' |
        sort -u |
        while IFS= read -r file; do
            [[ -f "${file}" ]] && printf '%s\n' "${file}"
        done
}

mapfile -t CHANGED_FILES < <(collect_changed_files)

collect_deleted_files() {
    {
        if [[ "${BASE_REF}" != "HEAD" ]] && git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
            git diff --name-only --diff-filter=D "${BASE_REF}...HEAD"
        fi
        git diff --name-only --diff-filter=D
        git diff --cached --name-only --diff-filter=D
    } |
        awk 'NF' |
        sort -u
}

mapfile -t DELETED_FILES < <(collect_deleted_files)

command -v uv >/dev/null 2>&1 || {
    echo "❌ uv is required" >&2
    exit 1
}

agent_gate_changed=false
for file in "${CHANGED_FILES[@]}"; do
    if [[ "${file}" == "scripts/agent-quality-gate.sh" ]]; then
        agent_gate_changed=true
        break
    fi
done

if [[ "${MODE}" != "fix" && "${agent_gate_changed}" == true ]]; then
    run_compact "agent gate shell formatting" \
        uv run pre-commit run shfmt --files scripts/agent-quality-gate.sh
    run_compact "agent gate shell lint" \
        uv run pre-commit run shell-lint --files scripts/agent-quality-gate.sh
    run_compact "agent gate shell style" \
        uv run pre-commit run bashate --files scripts/agent-quality-gate.sh
fi

if [[ "${MODE}" == "fix" ]]; then
    if ((${#CHANGED_FILES[@]} > 0)); then
        run_compact "apply/check pre-commit hooks on changed files" \
            uv run pre-commit run --hook-stage pre-commit \
            --files "${CHANGED_FILES[@]}" --show-diff-on-failure
    fi
    echo "ℹ️  review git diff/status, commit deterministic fixes, then run this gate and finally --publish"
    exit 0
fi

if [[ "${BASE_REF}" != "HEAD" ]]; then
    if ! git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
        printf '❌ QG_BASE_MISSING: comparison base %s is unavailable\n' "${BASE_REF}" >&2
        exit 1
    fi
    if ! git merge-base --is-ancestor "${BASE_REF}" HEAD; then
        printf '❌ QG_BASE_STALE: HEAD does not contain %s; update/rebase before publishing\n' "${BASE_REF}" >&2
        exit 1
    fi
    printf '✅ branch contains comparison base %s\n' "${BASE_REF}"
fi

large_deletion_failed=0
if [[ "${QUALITY_ALLOW_LARGE_DELETION:-0}" != "1" && "${BASE_REF}" != "HEAD" ]]; then
    for file in "${CHANGED_FILES[@]}"; do
        case "${file}" in
            uv.lock | Pipfile.lock | package-lock.json | trivy-sbom.json)
                continue
                ;;
            *.md | *.py | *.sh | *.js | *.mjs | *.css | *.yml | *.yaml | *.json | *.toml | Dockerfile* | Makefile)
                ;;
            *)
                continue
                ;;
        esac
        git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
        base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
        current_lines="$(wc -l <"${file}" | tr -d ' ')"
        if ((base_lines < 200 || current_lines >= base_lines)); then
            continue
        fi
        deleted_lines=$((base_lines - current_lines))
        deleted_percent=$((deleted_lines * 100 / base_lines))
        if ((deleted_lines >= 100 && deleted_percent >= 40)); then
            printf '❌ QG_LARGE_DELETION: %s lost %d/%d lines (%d%%); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
                "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}" >&2
            large_deletion_failed=1
        fi
    done

    for file in "${DELETED_FILES[@]}"; do
        case "${file}" in
            uv.lock | Pipfile.lock | package-lock.json | trivy-sbom.json)
                continue
                ;;
            *.md | *.py | *.sh | *.js | *.mjs | *.css | *.yml | *.yaml | *.json | *.toml | Dockerfile* | Makefile)
                ;;
            *)
                continue
                ;;
        esac
        git cat-file -e "${BASE_REF}:${file}" 2>/dev/null || continue
        base_lines="$(git show "${BASE_REF}:${file}" | wc -l | tr -d ' ')"
        if ((base_lines >= 200)); then
            printf '❌ QG_LARGE_DELETION: %s was deleted (%d lines); set QUALITY_ALLOW_LARGE_DELETION=1 only after explicit review\n' \
                "${file}" "${base_lines}" >&2
            large_deletion_failed=1
        fi
    done
fi
if ((large_deletion_failed != 0)); then
    exit 1
fi
printf '✅ destructive-diff guard\n'

exec_bit_failed=0
for file in "${CHANGED_FILES[@]}"; do
    IFS= read -r first_line <"${file}" || true
    [[ "${first_line:-}" == '#!'* ]] || continue
    if git ls-files --error-unmatch -- "${file}" >/dev/null 2>&1; then
        mode="$(git ls-files --stage -- "${file}" | awk 'NR == 1 {print $1}')"
        if [[ "${mode}" != "100755" ]]; then
            printf '❌ QG_EXEC_BIT: %s has a shebang but Git mode is %s; run git add --chmod=+x %q\n' \
                "${file}" "${mode:-unknown}" "${file}" >&2
            exec_bit_failed=1
        fi
    elif [[ ! -x "${file}" ]]; then
        printf '❌ QG_EXEC_BIT: untracked %s has a shebang but is not executable\n' "${file}" >&2
        exec_bit_failed=1
    fi
done
if ((exec_bit_failed != 0)); then
    exit 1
fi
printf '✅ executable-script contract\n'

if [[ "${PUBLISH}" == true ]]; then
    run_compact "canonical formatter/linter/security publication gate" \
        bash scripts/quality-gate.sh --publish
else
    run_compact "canonical formatter/linter/security gate" \
        bash scripts/quality-gate.sh
fi

CHANGED_PYTHON=()
for file in "${CHANGED_FILES[@]}"; do
    [[ "${file}" == *.py ]] && CHANGED_PYTHON+=("${file}")
done
if ((${#CHANGED_PYTHON[@]} > 0)); then
    run_compact "modified Python code-size gate" \
        uv run python scripts/check_code_size.py \
        --baseline-ref "${BASE_REF}" "${CHANGED_PYTHON[@]}"
fi

run_compact "release/version contract" uv run python scripts/check_versions.py
run_compact "repository pytest suite (fail-fast)" \
    uv run pytest -q --disable-warnings --maxfail=1 --junit-xml=junit.xml

if [[ "${PUBLISH}" == true ]]; then
    STATUS="$(git status --short)"
    if [[ -n "${STATUS}" ]]; then
        echo "❌ Working tree changed after tests; review generated output before publishing." >&2
        printf '%s\n' "${STATUS}" >&2
        exit 1
    fi
    echo "✅ Agent publication gate passed; repository is clean and safe to publish."
else
    echo "✅ Agent quality gate passed."
fi
