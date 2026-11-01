#!/usr/bin/env bash
set -euo pipefail

# One timeout, error, and log contract for full and isolated CI pytest runs.
# A deadline or SIGKILL always fails the gate; never suppress its exit code.
usage() {
    echo "usage: $0 {full|isolated} <command> [args...]" >&2
    exit 2
}

if (($# < 2)); then
    usage
fi
mode="$1"
shift

case "${mode}" in
    full)
        budget="12m"
        log="pytest.log"
        ;;
    isolated)
        budget="6m"
        log="$(mktemp "${TMPDIR:-/tmp}/ci-pytest.XXXXXXXX")"
        trap 'rm -f -- "${log}"' EXIT
        ;;
    *)
        usage
        ;;
esac

if ! command -v timeout >/dev/null 2>&1; then
    echo "::error::PYTEST_TOOL_MISSING: GNU timeout is required by CI." >&2
    exit 2
fi

started="${SECONDS}"
set +e
timeout --signal=TERM --kill-after=30s "${budget}" "$@" >"${log}" 2>&1
rc=$?
set -e

if [[ "${mode}" == "full" && -n "${GITHUB_OUTPUT:-}" ]]; then
    printf 'seconds=%d\n' "$((SECONDS - started))" >>"${GITHUB_OUTPUT}"
fi

if ((rc != 0)); then
    case "${rc}" in
        124)
            echo "::error::PYTEST_TIMEOUT: ${mode} suite exceeded ${budget}; inspect the last running test and faulthandler trace." >&2
            ;;
        137)
            echo "::error::PYTEST_KILLED: process received SIGKILL; investigate runner memory and timeout evidence." >&2
            ;;
        *)
            printf '::error::PYTEST_FAILED: %s suite returned exit %d.\n' "${mode}" "${rc}" >&2
            ;;
    esac
    echo "::group::pytest ${mode} failure · last 180 lines" >&2
    tail -n 180 "${log}" >&2 || true
    echo "::endgroup::" >&2
    exit "${rc}"
fi

if [[ "${mode}" == "isolated" ]]; then
    echo "✅ isolated pytest contracts passed"
    exit 0
fi

summary="$(tail -n 1 "${log}")"
printf '%s\n' "${summary}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '### pytest\n%s\n' "${summary}" >>"${GITHUB_STEP_SUMMARY}"
fi
