#!/usr/bin/env bash
# TrueNAS-only, local-first checks for the fastapi-sample PR #350 worktree.
# Run as a subprocess (bash script), never source it in an SSH shell.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$ROOT"

RUN_QUALITY=false
OFFLINE=false
SKIP_SYNC=false
usage() {
    echo 'Usage: bash scripts/truenas/run-pr350-tests.sh [--quality] [--offline] [--no-sync]'
}
for arg in "$@"; do
    case "$arg" in
        --quality) RUN_QUALITY=true ;;
        --offline) OFFLINE=true ;;
        --no-sync) SKIP_SYNC=true ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

# Never update or install dependencies in the live TrueNAS staging checkout.
if [[ "$ROOT" == /mnt/cpool/compose/nabla-compose/fastapi-sample ]]; then
    echo 'ERROR: use a detached PR worktree, not the deployed FastAPI submodule.' >&2
    exit 2
fi
if [[ ! -x /usr/bin/python3.13 ]]; then
    echo 'ERROR: TrueNAS /usr/bin/python3.13 is unavailable.' >&2
    exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
    echo 'ERROR: uv is not installed or not on PATH.' >&2
    exit 2
fi

# .python-version pins 3.13.15, which this TrueNAS does not have.
# The project's requires-python is ==3.13.*; use the installed 3.13.5.
export UV_PYTHON="/usr/bin/python3.13"
export UV_PYTHON_DOWNLOADS=never
printf 'Checkout: %s\nCommit: %s\n' "$ROOT" "$(git rev-parse HEAD)"
printf 'Interpreter: %s (%s)\n' "$UV_PYTHON" "$("$UV_PYTHON" --version)"
printf 'uv: %s\n' "$(uv --version)"

if [[ "$SKIP_SYNC" == false ]]; then
    sync_args=(sync --frozen --python "$UV_PYTHON")
    [[ "$OFFLINE" == true ]] && sync_args+=(--offline)
    uv "${sync_args[@]}"
elif [[ ! -x .venv/bin/python ]]; then
    echo 'ERROR: --no-sync requested but this worktree has no .venv.' >&2
    exit 2
fi

uv run --frozen --no-sync --python "$UV_PYTHON" python --version
uv run --frozen --no-sync --python "$UV_PYTHON" pytest -q \
    tests/unit/test_homelab_probe_deadline_phases.py \
    tests/unit/test_homelab_probe_timing.py \
    tests/unit/test_homelab_cycle_summary.py \
    tests/unit/test_agent_publication_proof.py

if [[ "$RUN_QUALITY" == true ]]; then
    # Only after targeted tests pass. The gate may modify files in --fix mode.
    bash scripts/agent-quality-gate.sh --fix
fi
printf '\nFinal worktree changes:\n'
git status --short
