#!/usr/bin/env bash
# Source only. Deadlines are failures, not skipped validations.
quality_run_bounded() {
    local seconds="$1"
    shift
    if ! [[ "$seconds" =~ ^[1-9][0-9]{0,4}$ ]] || (( 10#$seconds > 3600 )); then
        printf '❌ QG_TIMEOUT_INVALID: expected 1..3600 seconds, got %s\n' "$seconds" >&2
        return 2
    fi
    if ! command -v timeout >/dev/null 2>&1; then
        echo "❌ QG_TIMEOUT_TOOL_MISSING: GNU timeout is required." >&2
        return 2
    fi
    local rc
    if timeout --signal=TERM --kill-after=15s "${seconds}s" "$@"; then
        return 0
    else
        rc=$?
    fi
    case "$rc" in
        124) printf '❌ QG_STEP_TIMEOUT: command exceeded %ss (exit 124).\n' "$seconds" >&2 ;;
        137) echo '❌ QG_STEP_KILLED: command received SIGKILL (exit 137).' >&2 ;;
    esac
    return "$rc"
}
