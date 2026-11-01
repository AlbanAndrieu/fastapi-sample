#!/usr/bin/env bash
# Source only. One kernel-owned lock per worktree; no PID or stale lock cleanup.
quality_lock_acquire() {
    local path="$1"
    local old_umask
    if ! command -v flock >/dev/null 2>&1; then
        echo "❌ QG_LOCK_TOOL_MISSING: flock (util-linux) is required." >&2
        return 2
    fi
    if [[ -d "$path" ]]; then
        printf '❌ QG_LOCK_LEGACY_DIR: old lock directory at %s; check for a running agent before manual removal.\n' "$path" >&2
        return 75
    fi
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
        printf '❌ QG_LOCK_INVALID: lock path must be a regular file: %s\n' "$path" >&2
        return 2
    fi
    old_umask="$(umask)"
    umask 077
    if ! exec {QUALITY_LOCK_FD}>"$path"; then
        umask "$old_umask"
        echo "❌ QG_LOCK_OPEN_FAILED: cannot open worktree lock." >&2
        return 2
    fi
    umask "$old_umask"
    if ! flock -n "$QUALITY_LOCK_FD"; then
        printf '❌ QG_LOCKED: another quality gate holds the worktree lock (%s).\n' "$path" >&2
        echo "   Use a separate Git worktree for each agent." >&2
        exec {QUALITY_LOCK_FD}>&-
        return 75
    fi
    # Keep the descriptor open. The OS releases the lock on exit, SIGKILL,
    # and a hard crash. Do not unlink the file: doing so creates lock races.
}
