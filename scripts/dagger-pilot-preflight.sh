#!/usr/bin/env bash
# P1 Dagger pilot readiness only; this never starts an engine or a CI job.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo 'NOT READY: not inside a Git checkout' >&2
  exit 2
}
cd "$repo_root"

required=(git bash uv just dagger docker)
missing=()
for executable in "${required[@]}"; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    missing+=("$executable")
  fi
done
if (("${#missing[@]}" > 0)); then
  printf 'NOT READY: missing required executables: %s\n' "${missing[*]}" >&2
  exit 2
fi

if [[ ! -f dagger.json && ! -f .dagger/dagger.json ]]; then
  echo 'NOT READY: no reviewed Dagger module configuration' >&2
  exit 2
fi
if [[ ! -f dagger.lock && ! -f .dagger/dagger.lock ]]; then
  echo 'NOT READY: no checked-in Dagger lockfile' >&2
  exit 2
fi

# A generated or ignored lockfile is not a reviewed, reproducible input.
module_file=dagger.json
[[ -f "$module_file" ]] || module_file=.dagger/dagger.json
lock_file=dagger.lock
[[ -f "$lock_file" ]] || lock_file=.dagger/dagger.lock
for file in "$module_file" "$lock_file"; do
  if ! git ls-files --error-unmatch -- "$file" >/dev/null 2>&1; then
    printf 'NOT READY: Dagger input must be tracked in Git: %s\n' "$file" >&2
    exit 2
  fi
done

printf 'READY FOR MANUAL PILOT: SHA=%s; module and lockfile present\n' \
  "$(git rev-parse HEAD)"
printf 'This preflight does not prove native/Dagger parity, engine health or L3.\n'
