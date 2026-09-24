#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CI_SCOPE_SCRIPT="${SCRIPT_DIR}/ci-scope.sh"

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

tool_version_or_fail() {
    local label="$1"
    shift
    local value

    if ! command -v "$1" >/dev/null 2>&1; then
        printf '❌ QG_PUBLISH_TOOL_MISSING: required tool %s is unavailable\n' \
            "${label}" >&2
        return 1
    fi
    if ! value="$("$@" 2>&1)"; then
        printf '❌ QG_PUBLISH_TOOL_INVALID: failed to query %s version\n' \
            "${label}" >&2
        return 1
    fi
    printf '%s\n' "${value}"
}

toolchain_fingerprint() {
    local uv_version
    local python_version
    local precommit_version
    local lock_hash

    uv_version="$(tool_version_or_fail uv uv --version)" || return 1
    python_version="$(
        tool_version_or_fail python uv run --no-sync python --version
    )" || return 1
    precommit_version="$(
        tool_version_or_fail pre-commit uv run --no-sync pre-commit --version
    )" || return 1

    if [[ -f uv.lock ]]; then
        lock_hash="$(git hash-object uv.lock)"
    else
        lock_hash="missing"
    fi

    {
        printf 'uv=%s\n' "${uv_version}"
        printf 'python=%s\n' "${python_version}"
        printf 'pre-commit=%s\n' "${precommit_version}"
        printf 'uv-lock=%s\n' "${lock_hash}"
    } | git hash-object --stdin
}

BASE_REF="$(resolve_base_ref)"
if ! git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
    printf '❌ QG_PUBLISH_BASE_MISSING: comparison base %s is unavailable\n' \
        "${BASE_REF}" >&2
    exit 1
fi
if ! git merge-base --is-ancestor "${BASE_REF}" HEAD; then
    printf '❌ QG_PUBLISH_BASE_STALE: HEAD does not contain %s\n' \
        "${BASE_REF}" >&2
    exit 1
fi

STATUS="$(git status --short)"
if [[ -n "${STATUS}" ]]; then
    echo "❌ QG_PUBLISH_DIRTY: commit the intended batch before publication validation." >&2
    printf '%s\n' "${STATUS}" >&2
    exit 1
fi

HEAD_SHA="$(git rev-parse HEAD)"
BASE_SHA="$(git rev-parse "${BASE_REF}^{commit}")"
if ! TOOLCHAIN_SHA="$(toolchain_fingerprint)"; then
    exit 1
fi

PROOF_VERSION="v1"
PROOF_KEY="${PROOF_VERSION}|${HEAD_SHA}|${BASE_SHA}|${TOOLCHAIN_SHA}"
PROOF_FILE="$(git rev-parse --git-path agent-publication-proof)"

if [[ -f "${PROOF_FILE}" ]] && [[ "$(cat "${PROOF_FILE}")" == "${PROOF_KEY}" ]]; then
    echo "✅ QG_PUBLISH_PROOF_REUSED: HEAD/base/toolchain unchanged; strict publication gate already passed."
    exit 0
fi

QUALITY_BASE_REF="${BASE_SHA}" bash scripts/agent-quality-gate.sh --publish

scope_output="$(QUALITY_BASE_REF="${BASE_SHA}" bash "${CI_SCOPE_SCRIPT}")"
printf '%s\n' "${scope_output}"
build="$(awk -F= '$1 == "build" { print $2; exit }' <<<"${scope_output}")"

case "${build}" in
    true)
        uv run --no-sync pylint \
            --fail-under=9.5 \
            --disable=E1701,E0102,E1003 \
            server_app.py nabla

        uv run --no-sync python -c \
            "import nabla.main; assert nabla.main.app is not None"

        uv build
        ;;
    false)
        echo "✅ QG_PUBLISH_BUILD_SKIPPED: no application build impact in this publication scope."
        ;;
    *)
        printf '❌ QG_PUBLISH_SCOPE_INVALID: ci-scope returned build=%s\n' \
            "${build:-missing}" >&2
        exit 1
        ;;
esac

STATUS="$(git status --short)"
if [[ -n "${STATUS}" ]]; then
    echo "❌ QG_PUBLISH_DIRTY_AFTER_BUILD: tracked files changed during publication validation." >&2
    printf '%s\n' "${STATUS}" >&2
    exit 1
fi

mkdir -p "$(dirname "${PROOF_FILE}")"
PROOF_TMP="$(mktemp "${PROOF_FILE}.XXXXXX")"
trap 'rm -f "${PROOF_TMP}"' EXIT
printf '%s\n' "${PROOF_KEY}" >"${PROOF_TMP}"
mv "${PROOF_TMP}" "${PROOF_FILE}"
trap - EXIT

echo "✅ QG_PUBLISH_PROOF_WRITTEN: strict FastAPI publication proof cached for this HEAD/base/toolchain."
