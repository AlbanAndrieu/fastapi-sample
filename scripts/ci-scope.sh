#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--mode-only" ]]; then
    shift
    exec python3 "${SCRIPT_DIR}/ci_scope.py" --dependency-mode "$@"
fi

exec python3 "${SCRIPT_DIR}/ci_scope.py" "$@"
