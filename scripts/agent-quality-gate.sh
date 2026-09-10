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
    --dependency-mode)
        MODE="dependency"
        shift
        ;;
    -h | --help)
        cat <<'EOF'
Usage:
  bash scripts/agent-quality-gate.sh [--fix|--publish|--dependency-mode]

Modes:
  default            strict validation gate
  --fix              converge deterministic pre-commit rewrites, then validate the editing tree
  --publish          strict gate plus canonical clean-tree publication check
  --dependency-mode  print full, quality, or none for CI dependency provisioning

Environment:
  QUALITY_BASE_REF                 override comparison base
  QUALITY_LOG_TAIL                 failure log lines to print (default: 50, capped at 80)
  QUALITY_FIX_PASSES               maximum pre-commit convergence passes (default: 3)
  QUALITY_ALLOW_LARGE_DELETION=1   acknowledge all intentional large truncations/deletions
  QUALITY_LARGE_DELETION_ACK_FILE  reviewed-path acknowledgement file (default: .quality-gate-large-deletions)
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

LOG_TAIL="${QUALITY_LOG_TAIL:-50}"
if ((LOG_TAIL > 80)); then
    LOG_TAIL=80
fi
FIX_PASSES="${QUALITY_FIX_PASSES:-3}"
if ! [[ "${FIX_PASSES}" =~ ^[1-9][0-9]*$ ]]; then
    printf '❌ QUALITY_FIX_PASSES must be a positive integer\n' >&2
    exit 2
fi

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

full_pytest_impact=false
quality_contract_impact=false
classify_test_impact() {
    local file
    for file in "${CHANGED_FILES[@]}" "${DELETED_FILES[@]}"; do
        case "${file}" in
            tests/unit/test_agent_quality_gate_contract.py | scripts/agent-quality-gate.sh | scripts/quality-gate.sh | scripts/check_code_size.py | .github/workflows/* | .pre-commit* | mise.toml | AGENTS.md)
                quality_contract_impact=true
                ;;
            nabla/* | tests/* | server_app.py | pyproject.toml | uv.lock | Pipfile | Pipfile.lock | scripts/*.py)
                full_pytest_impact=true
                return
                ;;
        esac
    done
}

classify_test_impact
if [[ "${MODE}" == "dependency" ]]; then
    if [[ "${full_pytest_impact}" == true ]]; then
        echo "full"
    elif [[ "${quality_contract_impact}" == true ]]; then
        echo "quality"
    else
        echo "none"
    fi
    exit 0
fi

worktree_fingerprint() {
    {
        git diff --no-ext-diff --binary
        git diff --cached --no-ext-diff --binary
        while IFS= read -r file; do
            printf '%s\n' "${file}"
            git hash-object -- "${file}"
        done < <(git ls-files --others --exclude-standard | sort)
    } | git hash-object --stdin
}

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

converge_precommit_fixes() {
    if ((${#CHANGED_FILES[@]} == 0)); then
        echo "✅ no changed files require deterministic fixes"
        return 0
    fi

    local pass rc log before after
    for ((pass = 1; pass <= FIX_PASSES; pass++)); do
        before="$(worktree_fingerprint)"
        log="$(mktemp)"
        set +e
        uv run pre-commit run --hook-stage pre-commit \
            --files "${CHANGED_FILES[@]}" --show-diff-on-failure >"${log}" 2>&1
        rc=$?
        set -e
        after="$(worktree_fingerprint)"

        if ((rc == 0)); then
            rm -f "${log}"
            printf '✅ deterministic pre-commit fix converged in %d pass(es)\n' "${pass}"
            return 0
        fi

        if [[ "${before}" == "${after}" ]]; then
            printf '❌ QG_FIX_NO_PROGRESS: pre-commit failed without changing the tree on pass %d\n' "${pass}" >&2
            tail -n "${LOG_TAIL}" "${log}" >&2 || true
            rm -f "${log}"
            return "${rc}"
        fi

        printf '🔧 pre-commit pass %d/%d modified files; retrying on the rewritten tree\n' \
            "${pass}" "${FIX_PASSES}"
        if ((pass == FIX_PASSES)); then
            printf '❌ QG_FIX_NOT_CONVERGED: deterministic fixes still change files after %d passes\n' \
                "${FIX_PASSES}" >&2
            tail -n "${LOG_TAIL}" "${log}" >&2 || true
            rm -f "${log}"
            return "${rc}"
        fi
        rm -f "${log}"
        mapfile -t CHANGED_FILES < <(collect_changed_files)
    done
}

if [[ "${MODE}" == "fix" ]]; then
    converge_precommit_fixes
    mapfile -t CHANGED_FILES < <(collect_changed_files)
    mapfile -t DELETED_FILES < <(collect_deleted_files)
    full_pytest_impact=false
    quality_contract_impact=false
    classify_test_impact
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

LARGE_DELETION_ACK_FILE="${QUALITY_LARGE_DELETION_ACK_FILE:-.quality-gate-large-deletions}"
large_deletion_ack_file_changed=false
if [[ "${BASE_REF}" != "HEAD" && -f "${LARGE_DELETION_ACK_FILE}" ]]; then
    if ! git diff --quiet "${BASE_REF}...HEAD" -- "${LARGE_DELETION_ACK_FILE}"; then
        large_deletion_ack_file_changed=true
    fi
fi

is_large_deletion_acknowledged() {
    local file="$1"
    if [[ "${QUALITY_ALLOW_LARGE_DELETION:-0}" == "1" ]]; then
        return 0
    fi
    if [[ "${large_deletion_ack_file_changed}" != true ]]; then
        return 1
    fi
    grep -Fxq -- "${file}" "${LARGE_DELETION_ACK_FILE}"
}

large_deletion_failed=0
if [[ "${BASE_REF}" != "HEAD" ]]; then
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
            if is_large_deletion_acknowledged "${file}"; then
                printf '⚠️ QG_LARGE_DELETION_ACK: %s lost %d/%d lines (%d%%); reviewed path acknowledged by %s\n' \
                    "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}" "${LARGE_DELETION_ACK_FILE}"
            else
                printf '❌ QG_LARGE_DELETION: %s lost %d/%d lines (%d%%); review it and add the exact path to a changed %s, or set QUALITY_ALLOW_LARGE_DELETION=1 for an explicit global override\n' \
                    "${file}" "${deleted_lines}" "${base_lines}" "${deleted_percent}" "${LARGE_DELETION_ACK_FILE}" >&2
                large_deletion_failed=1
            fi
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
            if is_large_deletion_acknowledged "${file}"; then
                printf '⚠️ QG_LARGE_DELETION_ACK: %s was deleted (%d lines); reviewed path acknowledged by %s\n' \
                    "${file}" "${base_lines}" "${LARGE_DELETION_ACK_FILE}"
            else
                printf '❌ QG_LARGE_DELETION: %s was deleted (%d lines); review it and add the exact path to a changed %s, or set QUALITY_ALLOW_LARGE_DELETION=1 for an explicit global override\n' \
                    "${file}" "${base_lines}" "${LARGE_DELETION_ACK_FILE}" >&2
                large_deletion_failed=1
            fi
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

if [[ "${full_pytest_impact}" == true ]]; then
    run_compact "repository pytest suite (fail-fast)" \
        uv run pytest -q --disable-warnings --maxfail=1 --junit-xml=junit.xml
elif [[ "${quality_contract_impact}" == true ]]; then
    run_compact "quality-gate contract pytest (isolated fail-fast)" \
        env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q --noconftest \
        --disable-warnings --maxfail=1 \
        tests/unit/test_agent_quality_gate_contract.py --junit-xml=junit.xml
else
    echo "✅ pytest skipped: no Python/runtime/test or quality-gate contract impact"
fi

if [[ "${PUBLISH}" == true ]]; then
    STATUS="$(git status --short)"
    if [[ -n "${STATUS}" ]]; then
        echo "❌ Working tree changed after tests; review generated output before publishing." >&2
        printf '%s\n' "${STATUS}" >&2
        exit 1
    fi
    echo "✅ Agent publication gate passed; repository is clean and safe to publish."
elif [[ "${MODE}" == "fix" ]]; then
    echo "✅ Agent fix + validation gate passed. Review the final diff, commit once, then run --publish."
else
    echo "✅ Agent quality gate passed."
fi
