#!/usr/bin/env bash
# Source only. Lock supervisor owns the descriptor; commands never inherit it.
quality_lock_run() {
    local path="$1"
    shift

    if ! command -v flock >/dev/null 2>&1; then
        echo "❌ QG_LOCK_TOOL_MISSING: util-linux flock is required." >&2
        return 2
    fi
    if [[ -d "$path" ]]; then
        printf '❌ QG_LOCK_LEGACY_DIR: legacy directory at %s; verify agents before manual migration.\n' "$path" >&2
        return 75
    fi
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
        printf '❌ QG_LOCK_INVALID: expected a regular lock file: %s\n' "$path" >&2
        return 2
    fi

    local old_umask rc
    old_umask="$(umask)"
    umask 077
    if ! : >>"$path"; then
        umask "$old_umask"
        echo "❌ QG_LOCK_OPEN_FAILED: could not open worktree lock." >&2
        return 2
    fi
    umask "$old_umask"

    # -o closes the lock FD in the worker. Its subprocesses cannot keep a
    # phantom lock after the worker dies. The flock supervisor holds it until
    # the worker exits, including on SIGKILL. Never unlink this file.
    if flock -n -E 75 -o "$path" "$@"; then
        return 0
    else
        rc=$?
    fi
    if ((rc == 75)); then
        printf '❌ QG_LOCKED: another quality gate owns this worktree (%s).\n' "$path" >&2
        echo "   Use a separate Git worktree for each agent." >&2
    fi
    return "$rc"
}
