#!/usr/bin/env bash
# Per-worktree uv environment. Read-only default; explicit locked sync.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'BLOCKED: execute with bash; do not source this script.\n' >&2
  return 2
fi
set -Eeuo pipefail
mode="${1:---check}"
if [[ "$mode" == --help || "$mode" == -h ]]; then
  printf 'Usage: bash scripts/agent-worktree-python.sh [--check|--sync]\n'
  printf '%s\n' '--check is read-only; --sync explicitly installs locked dependencies.'
  exit 0
fi
[[ $# -le 1 && ( "$mode" == --check || "$mode" == --sync ) ]] || exit 2
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -f "$root/pyproject.toml" && -f "$root/uv.lock" ]] || {
  printf 'BLOCKED: pyproject.toml and uv.lock required\n' >&2
  exit 3
}
[[ ! -L "$root/.venv" ]] || {
  printf 'BLOCKED: symlinked .venv is forbidden\n' >&2
  exit 3
}
venv="$root/.venv"
if [[ "$mode" == --sync ]]; then
  command -v uv >/dev/null 2>&1 || {
    printf 'BLOCKED: uv missing; no global installation\n' >&2
    exit 3
  }
  ( cd -- "$root"
    unset VIRTUAL_ENV
    export UV_PROJECT_ENVIRONMENT="$venv"
    export UV_PYTHON_DOWNLOADS=never
    uv sync --locked --python 3.13.17
  ) || {
    printf 'BLOCKED: locked uv sync failed; quality not started\n' >&2
    exit 3
  }
fi
[[ -x "$venv/bin/python" ]] || {
  printf 'BLOCKED: worktree .venv missing; opt in with --sync\n' >&2
  exit 3
}
"$venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)' || {
  printf 'BLOCKED: FastAPI requires Python 3.13\n' >&2
  exit 3
}
printf 'PASS: isolated worktree Python 3.13; sync %s\n' "$( [[ "$mode" == --sync ]] && printf requested || printf not-requested )"
