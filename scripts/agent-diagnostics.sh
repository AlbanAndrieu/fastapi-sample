#!/usr/bin/env bash
# Safe by default: no network, secrets or runtime access in API-only sessions.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${AGENT_EXECUTION_MODE:-offline}"
action=static
plan=0
while (($#)); do
  case "${1}" in
    --mode)
      [[ $# -ge 2 ]] || { echo 'ERROR: --mode needs offline|workstation' >&2; exit 2; }
      mode="${2}"
      shift
      ;;
    --static) action=static ;;
    --runtime) action=runtime ;;
    --dns-only) action=dns ;;
    --metrics-lan) action=metrics-lan ;;
    --metrics-both) action=metrics-both ;;
    --plan) plan=1 ;;
    --help|-h)
      echo "Usage: $0 [--mode offline|workstation] [--static|--runtime|--dns-only|--metrics-lan|--metrics-both] [--plan]"
      echo 'Default offline; runtime/DNS/metrics require explicit workstation access.'
      exit 0
      ;;
    *) echo "ERROR: unknown option ${1}" >&2; exit 2 ;;
  esac
  shift
done
[[ "${mode}" == offline || "${mode}" == workstation ]] || {
  echo 'ERROR: AGENT_EXECUTION_MODE must be offline or workstation' >&2
  exit 2
}
# CI and Codex cannot opt into workstation probes, even if an inherited
# environment variable or explicit flag incorrectly selects that mode.
if [[ "${mode}" == workstation && ( -n "${CI:-}" || -n "${CODEX_HOME:-}" || -n "${CODEX_THREAD_ID:-}" ) ]]; then
  echo 'NOT_RUN: CI/Codex sessions cannot execute workstation probes' >&2
  exit 2
fi
if [[ "${action}" != static && "${mode}" != workstation ]]; then
  echo 'NOT_RUN: runtime, LAN DNS and metrics require explicit workstation mode' >&2
  exit 2
fi
case "${action}" in
  static) command=(bash "${root}/scripts/agent-offline-check.sh") ;;
  runtime) command=(bash "${root}/scripts/truenas-runtime-evidence.sh" --vantage workstation --quick) ;;
  dns) command=(bash "${root}/scripts/truenas-runtime-evidence.sh" --vantage workstation --dns-only) ;;
  metrics-lan) command=(python3 "${root}/scripts/verify-prometheus-cloud-projection.py" --check --scope lan) ;;
  metrics-both) command=(python3 "${root}/scripts/verify-prometheus-cloud-projection.py" --check --scope both) ;;
esac
if ((plan)); then
  printf 'PLAN mode=%s action=%s (NOT_RUN):' "${mode}" "${action}"
  printf ' %q' "${command[@]}"
  printf '\n'
  exit 0
fi
exec "${command[@]}"
