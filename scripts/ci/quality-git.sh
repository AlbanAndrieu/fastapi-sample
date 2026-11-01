#!/usr/bin/env bash
# Shared, side-effect-free Git reference policy for quality and publication.
# Source this file; it must not change cwd, traps, or shell options.

quality_git_commit_exists() {
    git rev-parse --verify --quiet "$1^{commit}" >/dev/null 2>&1
}

quality_resolve_base_ref() {
    local configured origin_head candidate
    configured="${QUALITY_BASE_REF:-}"

    # Explicit operator choice must resolve; never silently check a weaker base.
    if [[ -n "${configured}" ]]; then
        if ! quality_git_commit_exists "${configured}"; then
            printf '❌ QG_BASE_MISSING: QUALITY_BASE_REF is not a commit: %s\n' "${configured}" >&2
            return 2
        fi
        printf '%s\n' "${configured}"
        return 0
    fi

    # Prefer the remote's declared default branch, including detached worktrees.
    if origin_head="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)" &&
        quality_git_commit_exists "${origin_head}"; then
        printf '%s\n' "${origin_head}"
        return 0
    fi

    for candidate in origin/master origin/main; do
        if quality_git_commit_exists "${candidate}"; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done

    # A standalone fixture or shallow worktree may lack remote references.
    # The later ancestry/clean-tree checks still apply.
    if quality_git_commit_exists HEAD~1; then
        printf 'HEAD~1\n'
    elif quality_git_commit_exists HEAD; then
        printf 'HEAD\n'
    else
        printf '❌ QG_BASE_MISSING: no usable Git commit\n' >&2
        return 2
    fi
}
