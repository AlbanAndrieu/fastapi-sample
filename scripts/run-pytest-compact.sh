set -euo pipefail

LOG="${PYTEST_LOG_FILE:-${TMPDIR:-/tmp}/fastapi-sample-pytest-$(date +%Y%m%d-%H%M%S)-$.log}"
FAILURE_LINES="${PYTEST_FAILURE_SUMMARY_LINES:-20}"
if ! [[ "${FAILURE_LINES}" =~ ^[0-9]+$ ]]; then
  printf '❌ PYTEST_FAILURE_SUMMARY_LINES must be a non-negative integer\n' >&2
  exit 2
fi
if ((FAILURE_LINES > 40)); then
  FAILURE_LINES=40
fi

mkdir -p "$(dirname "${LOG}")"

set +e
uv run --no-sync pytest \
  -q \
  -p no:sugar \
  --disable-warnings \
  --tb=short \
  "$@" >"${LOG}" 2>&1
rc=$?
set -e

if ((rc == 0)); then
  summary="$(
    grep -E '(^Results \(|[0-9]+ passed|[0-9]+ skipped)' "${LOG}" |
      tail -n 1 || true
  )"
  [[ -n "${summary}" ]] || summary="$(tail -n 1 "${LOG}")"
  printf '✅ pytest: %s\n' "${summary}"
  rm -f "${LOG}"
  exit 0
fi

printf '❌ pytest failed (exit=%d) · full log: %s\n' "${rc}" "${LOG}" >&2
if ((FAILURE_LINES > 0)); then
  summary="$(
    grep -E '^(FAILED|ERROR) |^Results \(|^[[:space:]]+[0-9]+ (passed|failed|skipped)|=+ short test summary|=+ .*failed' "${LOG}" |
      tail -n "${FAILURE_LINES}" || true
  )"
  if [[ -n "${summary}" ]]; then
    printf '%s\n' "${summary}" >&2
  else
    # Import and collection failures may not generate a pytest summary.
    tail -n "${FAILURE_LINES}" "${LOG}" >&2
  fi
fi

exit "${rc}"
